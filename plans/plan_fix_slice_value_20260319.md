# Plan: Fix slice_value and slice_rule_id not populated in fact_values

## Context

Four bugs prevent `slice_value` and `slice_rule_id` from being written to `metrics.fact_values`.
The full audit is in the previous conversation. This plan fixes all four in priority order.

---

## Files to Modify

### 1. `pipelines/assets/metrics/velocity.py` — BUG #1 (Critical)

**Line 377**: Change `issues_df` to `issues_for_slicing`.

Current:
```python
sliced_wide = apply_slicing(
    issues_df,
    rules_df.filter(pl.col("slice_rule_id") == rule_id),
    velocity_slice_calc,
    engine=engine,
    source_table="clean_jira.issues"
)
```

Fix:
```python
sliced_wide = apply_slicing(
    issues_for_slicing,
    rules_df.filter(pl.col("slice_rule_id") == rule_id),
    velocity_slice_calc,
    engine=engine,
    source_table="clean_jira.issues"
)
```

`issues_for_slicing` is created on line 352 with `issue_type` alias for `type_name` and is the correct DataFrame to pass.

---

### 2. `pipelines/calculations/slicing_utils.py` — BUG #3 (Critical) + BUG #4 (Secondary)

**BUG #3 — Fix SmartSlicer `full_target` construction (line 108)**

The current logic constructs `full_target = f"{target_schema_table}.{group_col}"` where `target_schema_table = rule.get("source_table", ...)`. This is WRONG because `source_table` from the rule (`clean_jira.issues`) is NOT the target table for SmartSlicer — SmartSlicer needs the table that actually CONTAINS the dimension column.

Fix: when `source_table` in the rule is the same as the `source_table` parameter passed to `apply_slicing`, fall through to SmartSlicer with a corrected target. Specifically, use `group_col` as a column to look up on the source table or its FK-reachable neighbors. SmartSlicer's BFS will find the path.

Change line 108 from:
```python
full_target = f"{target_schema_table}.{group_col}"
```
To: construct the target using the SmartSlicer's schema graph to find which table has `group_col` reachable from `source_table`. If `target_schema_table != source_table`, use `f"{target_schema_table}.{group_col}"` (existing correct case). If they are the same (seed data pattern: source_table='clean_jira.issues', group_col='issue_type'), then do a BFS column search across reachable tables to find which neighbor table has a column matching `group_col` or `group_col` stripped of table-prefix.

Simpler pragmatic fix: check if `group_col` contains a dot — if it does, it already specifies `table.column`. Otherwise, search through FK-adjacent tables. Implementation:

```python
# If group_col looks like 'table.column', use as-is for SmartSlicer target
if '.' in group_col:
    full_target = f"{target_schema_table.split('.')[0]}.{group_col}"
else:
    # target_schema_table is source table; SmartSlicer needs target.column
    # Try to resolve: find an FK-adjacent table that has this column
    full_target = slicer.find_target_for_column(source_table, group_col)
    if not full_target:
        print(f"Warning: Cannot resolve target for column '{group_col}' from {source_table}")
        continue
    mapping_df = slicer.get_slice_mapping(source_table, full_target)
```

Add `find_target_for_column(source_table, col_name)` method to `SmartSlicer` (see section 3).

**BUG #4 — Fix heuristic `{group_col}_name` (line 102)**

Current heuristic: `f"{group_col.lower()}_name"` — for `issue_type` this yields `issue_type_name`, but the actual column is `type_name`.

Add a more robust check: also try stripping common prefixes. Specifically, try removing the first word of `group_col` to get the suffix:
- `issue_type` → strip `issue_` → `type` → check `type_name` ✓

```python
# Existing checks
if group_col.lower() in df_cols_lower:
    target_col = df_cols_lower[group_col.lower()]
elif f"{group_col.lower()}_name" in df_cols_lower:
    target_col = df_cols_lower[f"{group_col.lower()}_name"]
else:
    # Try suffix: 'issue_type' -> 'type' -> 'type_name'
    parts = group_col.lower().split('_')
    for i in range(1, len(parts)):
        suffix = '_'.join(parts[i:])
        if suffix in df_cols_lower:
            target_col = df_cols_lower[suffix]
            break
        if f"{suffix}_name" in df_cols_lower:
            target_col = df_cols_lower[f"{suffix}_name"]
            break
```

---

### 3. `pipelines/utils/smart_slicer.py` — Support for BUG #3 fix

Add method `find_target_for_column(self, source_table: str, col_name: str) -> Optional[str]`:

```python
def find_target_for_column(self, source_table: str, col_name: str) -> Optional[str]:
    """
    Search FK-adjacent tables (1 hop) for a table containing col_name.
    Returns schema.table.col_name string for get_slice_mapping, or None.
    """
    graph = self._get_schema_graph()
    inspector = inspect(self.engine)
    schema = source_table.split('.')[0]

    # Check source table itself first
    src_table_name = source_table.split('.')[1]
    src_cols = [c['name'] for c in inspector.get_columns(src_table_name, schema=schema)]
    if col_name in src_cols:
        return f"{source_table}.{col_name}"

    # Check FK neighbors (1 hop)
    for (neighbor, local_col, ref_col) in graph.get(source_table, []):
        neighbor_schema, neighbor_table = neighbor.split('.', 1)
        try:
            neighbor_cols = [c['name'] for c in inspector.get_columns(neighbor_table, schema=neighbor_schema)]
            if col_name in neighbor_cols:
                return f"{neighbor}.{col_name}"
        except Exception:
            continue
    return None
```

---

### 4. `scripts/seed_metric_store.py` — BUG #2 (Wrong seed data)

**Lines 187-189**: The seeded `group_by_source_column` values `issue_type` and `priority` do not exist as columns in `clean_jira.issues`.

With the fixes above (BUG #1 fix + heuristic fix), `issue_type` will work because `issues_for_slicing` has the column. However, `priority` still won't exist. Update the seed to use correct values that SmartSlicer can resolve OR that exist in `issues_for_slicing`.

Option A (direct column match — requires explicit alias in velocity.py):
- Keep `('By Issue Type', 'clean_jira.issues', 'issue_type', true)` — works after BUG #1 fix
- Change `('By Priority', 'clean_jira.issues', 'priority', true)` — leave for now or remove if `priority` not available

Option B (SmartSlicer convention from fix_slice_rules.py):
- `('By Issue Type', 'clean_jira.issue_types', 'name', true)`
- `('By Sprint', 'clean_jira.sprints', 'name', true)`

**Recommended**: Use Option B — it's consistent with `fix_slice_rules.py` and SmartSlicer's FK-traversal design. Also add a migration or data fix script that clears old rules and inserts correct ones.

Create `scripts/migrate_slice_rules_to_smartslicer.py`:
- DELETE FROM metrics.slice_rules
- INSERT correct rules using SmartSlicer convention

---

## Summary of Changes

| File | Change | Bug Fixed |
|------|--------|-----------|
| `pipelines/assets/metrics/velocity.py:377` | `issues_df` → `issues_for_slicing` | #1 |
| `pipelines/calculations/slicing_utils.py:99-103` | Enhanced heuristic column matching | #4 |
| `pipelines/calculations/slicing_utils.py:107-123` | Fix full_target construction using find_target_for_column | #3 |
| `pipelines/utils/smart_slicer.py` | Add `find_target_for_column` method | #3 |
| `scripts/seed_metric_store.py:187-189` | Update seed data to SmartSlicer convention | #2 |

## Testing

After changes, run:
```bash
python -m pytest tests/unit/test_slicing_utils.py tests/unit/test_smart_slicer.py -v
```

All existing tests must pass. The test `test_apply_slicing_basic_exact_match` validates BUG #1 fix behavior (exact column match). The test `test_apply_slicing_dynamic_injection` validates SmartSlicer path.
