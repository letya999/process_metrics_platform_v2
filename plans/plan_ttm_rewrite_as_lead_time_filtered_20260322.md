# Plan: Rewrite TTM as Lead Time with Issue Type Filter from calculation_settings

**Date:** 2026-03-22
**Branch:** metrics-expansion-and-calculation-unification

---

## Problem

`ttm_days` has `uses_commitment_points = true` and is architecturally the same metric as `lead_time_days`,
but filtered to specific issue types (e.g., only Epics). The current implementation is wrong:
- `pipelines/calculations/time_to_market.py` uses `jira_created_at` as the start point
- `pipelines/assets/metrics/time_to_market.py` calls the wrong calculation logic
- `metrics.calculation_settings` table is empty (no issue type filter configured)
- No commitment rules exist for `ttm_days` (should fall back to `lead_time_days` rules)

## Correct Architecture

TTM = `calculate_lead_time_per_issue` (same function as Lead Time) applied to:
- Issues filtered by type per `calculation_settings` (e.g., only "Epic")
- Same commitment zone as `lead_time_days` (uses `lead_time_days` rules as fallback when no `ttm_days` rules exist)
- Same output shape: `commitment_start_at → commitment_end_at`, `lead_time_days` as value, CEIL rounding

---

## Part 1: New Migration — Seed `calculation_settings` for `ttm_days`

**File to create:** `db/migrations/versions/0028_add_ttm_calculation_settings.py`

Migration must:
1. Insert one global record into `metrics.calculation_settings`:
   - `target_calculation_id` = (SELECT id FROM metrics.calculations WHERE calc_code = 'ttm_days')
   - `settings_type` = `'issue_type_filter'`
   - `settings_json` = `{"include": ["Epic"]}`
   - `project_id` = NULL (global default)
   - `enabled` = true
2. `downgrade()` must delete that row

Migration format matches existing migrations (revision = "0028", down_revision = "0027").

---

## Part 2: Rewrite `pipelines/calculations/time_to_market.py`

**Replace the entire file content.**

The new module provides one utility function used by the asset:

```python
def load_issue_type_filter(engine, calc_code: str, project_id: str = None) -> list[str]:
    """
    Load issue type names from calculation_settings for a given calc_code.
    Priority: project-specific setting > global setting.
    Returns list of type names (e.g., ["Epic"]).
    Fallback: ["Epic"] if no settings found.
    """
```

This function queries `metrics.calculation_settings` joined to `metrics.calculations`
where `settings_type = 'issue_type_filter'` and `enabled = true`.
It picks project-specific over global (NULL project_id).
Returns `settings_json["include"]` as a list of strings.
Fallback return value is `["Epic"]`.

No other functions needed. Remove all old TTM calculation logic.

---

## Part 3: Rewrite `pipelines/assets/metrics/time_to_market.py`

**Replace the asset logic entirely.** Keep the same asset name (`calculate_time_to_market`) and
`@asset` decorator deps, but change deps to match what lead_time uses:

```python
deps=[
    "clean_jira_issues",
    "clean_jira_issue_types",
    "clean_jira_boards",
    "clean_jira_board_columns",
    "clean_jira_issue_status_changelog",
]
```

Remove deps: `clean_jira_releases`, `clean_jira_release_issues` (no longer needed).

### New asset logic:

```python
def calculate_time_to_market(context, database):
    engine = database.get_engine()
    calc_id = get_calculation_id(engine, "ttm_days")

    # 1. Load issues with type info
    issues_df = read_table(engine, """
        SELECT i.id, i.project_id, i.external_key AS key, it.name AS type_name,
               i.jira_created_at, i.jira_resolved_at, p.external_key AS project_key
        FROM clean_jira.issues i
        JOIN clean_jira.projects p ON i.project_id = p.id
        LEFT JOIN clean_jira.issue_types it ON i.type_id = it.id
    """)

    if issues_df.is_empty():
        return {"status": "skipped", "reason": "No issues found"}

    project_agg_map = {pid: get_project_agg_id(engine, pid) for pid in issues_df["project_id"].unique()}

    # 2. Load changelog, boards, board_columns (same as lead_time asset)
    status_changelog_df = ...
    boards_df = ...
    board_columns_df = ...

    # 3. Load commitment rules for ttm_days; fall back to lead_time_days rules
    ttm_rules = load_commitment_rules_for_calc(engine, "ttm_days")
    if not ttm_rules:
        ttm_rules = load_commitment_rules_for_calc(engine, "lead_time_days")

    # 4. Load issue type filter from calculation_settings
    #    Use ttm_logic.load_issue_type_filter(engine, "ttm_days")
    #    Returns e.g. ["Epic"]
    global_type_filter = ttm_logic.load_issue_type_filter(engine, "ttm_days")

    # 5. For each board, apply type filter and calculate lead time
    all_ttm = []
    for board in boards_df.to_dicts():
        b_id = board["id"]
        p_id = board["project_id"]

        # Project-specific type filter (may differ per project)
        type_filter = ttm_logic.load_issue_type_filter(engine, "ttm_days", project_id=p_id)

        # Resolve commitment points
        rule = resolve_rule_from_cache(ttm_rules, p_id, b_id)
        if rule:
            points = identify_commitment_points_from_rule(rule, board_columns_df.filter(pl.col("board_id") == b_id))
        else:
            points = identify_commitment_points_heuristic(board_columns_df.filter(pl.col("board_id") == b_id))

        if not points["middle_status_ids"] or not points["end_status_ids"]:
            continue

        # Filter issues: project AND type
        project_issues = issues_df.filter(
            (pl.col("project_id") == p_id) &
            (pl.col("type_name").is_in(type_filter))
        )
        if project_issues.is_empty():
            continue

        # Calculate using the SAME function as lead_time
        ttm_df = lead_time_logic.calculate_lead_time_per_issue(
            project_issues,
            status_changelog_df,
            points["middle_status_ids"],
            points["end_status_ids"],
        )

        if not ttm_df.is_empty():
            ttm_df = ttm_df.with_columns(
                pl.lit(points.get("commitment_rule_id")).cast(pl.Utf8).alias("commitment_rule_id")
            )
            all_ttm.append(ttm_df)

    if not all_ttm:
        return {"status": "no_data"}

    base_ttm_wide = pl.concat(all_ttm).unique(subset=["issue_id"])

    # 6. Transform to fact_values (same pattern as lead_time asset)
    # time_id = commitment_end_at (YYYYMMDD)
    # event_start_at = commitment_start_at
    # event_end_at = commitment_end_at
    # value = lead_time_days (reused column, represents TTM in same unit)
    ...

    rows_written = write_fact_values(...)
    return {"status": "success", "rows_written": rows_written}
```

The `transform_to_fact_values` function should be identical to the one in the lead_time asset,
just using `commitment_end_at` as `time_id` and `lead_time_days` as `value`.

---

## Part 4: Update `tests/unit/test_time_to_market.py`

**Replace the entire test file.**

New tests for the new behavior:

1. **`test_load_issue_type_filter_returns_default_when_no_settings`**
   - Mock engine returns empty DataFrame
   - Assert returns `["Epic"]`

2. **`test_load_issue_type_filter_returns_global_setting`**
   - Mock engine returns global setting `{"include": ["Epic", "Feature"]}`
   - Assert returns `["Epic", "Feature"]`

3. **`test_load_issue_type_filter_prefers_project_specific_over_global`**
   - Global: `{"include": ["Epic"]}`
   - Project-specific: `{"include": ["Story"]}`
   - project_id = that project's id
   - Assert returns `["Story"]`

4. **`test_ttm_uses_same_logic_as_lead_time`**
   - Scenario: 2 issues in project:
     - Epic: went In Progress → Done (should be included)
     - Story: went In Progress → Done (should be excluded by type filter)
   - type_filter = ["Epic"]
   - Call `calculate_lead_time_per_issue` with filtered issues
   - Assert only 1 result (the Epic)

5. **`test_ttm_excludes_issues_without_commitment_zone_transition`**
   - Epic that went To Do → Done only (no In Progress)
   - Assert excluded (same as lead_time behavior - INNER JOIN, no fallback)

6. **`test_ttm_uses_ceil_rounding`**
   - Epic with 5 hours elapsed
   - Assert `lead_time_days == 1.0`

---

## Files to Modify

1. **CREATE** `db/migrations/versions/0028_add_ttm_calculation_settings.py` — seed global Epic filter
2. **REWRITE** `pipelines/calculations/time_to_market.py` — new `load_issue_type_filter()` utility only
3. **REWRITE** `pipelines/assets/metrics/time_to_market.py` — use `calculate_lead_time_per_issue` + type filter
4. **REWRITE** `tests/unit/test_time_to_market.py` — tests for new behavior

## Files NOT to Modify

- `pipelines/calculations/lead_time.py` — already correct
- `pipelines/assets/metrics/lead_time.py` — already correct
- `tests/unit/test_lead_time_logic.py` — already updated in previous task

---

## Important Implementation Notes

### `load_issue_type_filter` caching note
In the asset, call `load_issue_type_filter` ONCE with `project_id=None` to get global default.
Then for each board/project, call again with `project_id=p_id` if there might be project-specific overrides.
OR: load ALL settings in one DB query and resolve in Python (prefer this for performance).

### No releases/fix_versions needed
Remove all `releases_df` and `issue_fix_versions_df` from the asset. TTM is now purely
commitment-zone based, not release-date based. The "released_at" concept is replaced by
`commitment_end_at` (first Done after commitment start).

### Imports in new asset
```python
from pipelines.calculations import lead_time as lead_time_logic
from pipelines.calculations import time_to_market as ttm_logic
from pipelines.calculations.commitment_resolver import (
    identify_commitment_points_from_rule,
    identify_commitment_points_heuristic,
    load_commitment_rules_for_calc,
    resolve_rule_from_cache,
)
```

---

## Verification

After implementation, run:
```bash
python -m pytest tests/unit/test_time_to_market.py -v
```

All tests must pass (green).

Run the migration:
```bash
docker exec postgres psql -U postgres -d process_metrics_v2 -c "SELECT settings_type, settings_json FROM metrics.calculation_settings LIMIT 5"
```

Should show the seeded Epic filter row.
