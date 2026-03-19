# Plan: Slicing Diagnostics + Fix Migration

## Problem

After code fixes, `slice_value` and `slice_rule_id` are still NULL in `fact_values`.
Root causes to investigate:
1. `metrics.slice_rules` in DB still has old data (`issue_type`, `priority` for `clean_jira.issues`)
2. `migrate_slice_rules_to_smartslicer.py` has broken `ON CONFLICT (rule_name)` — there is NO UNIQUE constraint on `rule_name` in the migration schema
3. SmartSlicer might still fail to find path even with correct rules
4. `issues_for_slicing` might have no data for the dimension column after join

## Task 1: Create `scripts/diagnose_slicing.py`

This script must be runnable standalone (`python scripts/diagnose_slicing.py`) and must:

**Step 1 — DB State**
- Connect to DB using same env vars as `migrate_slice_rules_to_smartslicer.py`
- Print all rows from `metrics.slice_rules` with all columns
- Print `metrics.definitions` row for `metric_code='velocity'`
- Print count of `fact_values` WHERE slice_rule_id IS NOT NULL
- Print count of `fact_values` WHERE slice_rule_id IS NULL

**Step 2 — get_slice_rules simulation**
- Get velocity def_id from `metrics.definitions WHERE metric_code='velocity'`
- Call `get_slice_rules(engine, target_definition_id=def_id)` directly (import from pipelines)
- Print the returned DataFrame (all columns)
- If empty, print "PROBLEM: no rules returned for velocity def_id=<uuid>"

**Step 3 — SmartSlicer path test**
- For each rule returned, instantiate `SmartSlicer(engine)`
- Call `find_target_for_column('clean_jira.issues', rule.group_by_column)`
- Print result: found target or None
- If target found, call `get_slice_mapping('clean_jira.issues', target)` and print first 5 rows
- If None, print "PROBLEM: cannot resolve column <group_by_column> from clean_jira.issues"

**Step 4 — issues_for_slicing test**
- Query `SELECT i.id, i.project_id, it.name AS type_name FROM clean_jira.issues i LEFT JOIN clean_jira.issue_types it ON i.type_id = it.id LIMIT 5`
- Print unique type_name values (sample)
- Print "issue_type alias would produce: <values>"

**Step 5 — Full trace**
- Query `SELECT * FROM metrics.v_facts WHERE slice_rule_name IS NOT NULL LIMIT 5`
- If empty: print "PROBLEM: No sliced facts in v_facts"
- If rows: print them

## Task 2: Fix `scripts/migrate_slice_rules_to_smartslicer.py`

The current script has `ON CONFLICT (rule_name)` which fails silently because there is NO UNIQUE constraint on `rule_name` in `metrics.slice_rules` table (confirmed in migration 0018).

Fix: Remove ON CONFLICT clause. The script already does DELETE before INSERT so duplicates won't arise. Rewrite as:

```sql
-- Step 1: Delete all existing rules (already done in script)
DELETE FROM metrics.slice_rules WHERE rule_name IN ('By Issue Type', 'By Priority', 'By Sprint');

-- Step 2: Insert correct rules (no ON CONFLICT needed after DELETE)
INSERT INTO metrics.slice_rules (rule_name, source_table, group_by_source_column, enabled) VALUES
('By Issue Type', 'clean_jira.issue_types', 'name', true),
('By Sprint', 'clean_jira.sprints', 'name', true);
```

Also add verification at end: after insert, SELECT and print all rows from metrics.slice_rules to confirm.

## Task 3: Fix `scripts/seed_metric_store.py` seed_slice_rules function

Remove `ON CONFLICT (rule_name)` since there is no unique constraint. Use `ON CONFLICT DO NOTHING` or just plain INSERT after DELETE. The safest approach:

```sql
DELETE FROM metrics.slice_rules;
INSERT INTO metrics.slice_rules (rule_name, source_table, group_by_source_column, enabled) VALUES
('By Issue Type', 'clean_jira.issue_types', 'name', true),
('By Sprint', 'clean_jira.sprints', 'name', true);
```

## Files to Create/Modify

- CREATE `scripts/diagnose_slicing.py` — standalone diagnostic script
- MODIFY `scripts/migrate_slice_rules_to_smartslicer.py` — fix ON CONFLICT, add verification output
- MODIFY `scripts/seed_metric_store.py` — fix seed_slice_rules() to not use broken ON CONFLICT

## Notes

- The diagnose script must be runnable STANDALONE without Dagster — use direct SQLAlchemy
- Import `get_slice_rules` and `SmartSlicer` from pipelines package using sys.path manipulation if needed
- Print clear PASS/FAIL indicators for each check
- Do NOT run the migration inside this plan — user will run it manually after seeing diagnose output
