# Phase 5: External ID Indexes + Sprint Property Changelog

**Branch:** `fix/jira-pipeline-clean-layer-integrity`
**Goal:** Two improvements: (5.1) add external_id indexes for faster JOIN performance; (5.4) upgrade sprint_changelog to full daily snapshot-diff.

---

## Task 5.1 — External ID indexes

### Problem
`external_id` columns in clean_jira tables are TEXT type (Jira returns IDs as strings). The UNIQUE constraints are composite `(project_id, external_id)`, which helps multi-column queries but not single-column `WHERE external_id = :x` lookups used in JOIN chains from raw to clean.

### What to create
**New file:** `db/migrations/add_external_id_indexes.sql`

```sql
-- Standalone external_id indexes for fast JOIN from raw layer to clean layer
-- Safe to run multiple times (IF NOT EXISTS)

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_cj_issues_ext_id
    ON clean_jira.issues(external_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_cj_sprints_ext_id
    ON clean_jira.sprints(external_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_cj_releases_ext_id
    ON clean_jira.releases(external_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_cj_jira_users_ext_id
    ON clean_jira.jira_users(external_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_cj_sprint_changelog_sprint_id_field
    ON clean_jira.sprint_changelog(sprint_id, field_name, changed_at DESC);
```

The last index on `sprint_changelog(sprint_id, field_name, changed_at DESC)` supports the DISTINCT ON query used in the new snapshot-diff logic (Task 5.4).

**No Python asset changes needed for 5.1.**

---

## Task 5.4 — Sprint property changelog (snapshot-diff upgrade)

### Problem
Current `clean_jira_sprint_changelog` asset records only one event per sprint: "sprint closed". Fields `name`, `goal`, `start_date`, `end_date` changes are never captured.

### Schema compatibility
The `clean_jira.sprint_changelog` table already has the correct schema:
```sql
sprint_id uuid, field_name text, old_value text, new_value text, changed_by_id uuid, changed_at timestamptz
```
**No schema migration needed.** Existing rows (status=closed, old_value=NULL) are fully compatible with new logic.

### New asset logic
Replace the SQL in `clean_jira_sprint_changelog` with snapshot-diff approach identical to `clean_jira_release_changelog` (Phase 3).

**Tracked fields:** `name`, `goal`, `start_date`, `end_date`, `status`

**Algorithm:**
1. Get last known value per (sprint_id, field_name) using `DISTINCT ON ... ORDER BY changed_at DESC`
2. Cross-join with current sprint values (UNION ALL per field)
3. Insert rows where `current_value IS DISTINCT FROM last_known_value`
4. On first run: `last_known_value IS NULL` → bootstrap all current values (old_value=NULL)

**New SQL structure:**
```sql
WITH last_known AS (
    SELECT DISTINCT ON (sprint_id, field_name)
        sprint_id, field_name, new_value
    FROM clean_jira.sprint_changelog
    ORDER BY sprint_id, field_name, changed_at DESC
),
current_fields AS (
    SELECT id AS sprint_id, 'name'       AS field_name, name           AS current_value FROM clean_jira.sprints
    UNION ALL
    SELECT id, 'goal',       goal                                                        FROM clean_jira.sprints
    UNION ALL
    SELECT id, 'start_date', start_date::text                                            FROM clean_jira.sprints
    UNION ALL
    SELECT id, 'end_date',   end_date::text                                              FROM clean_jira.sprints
    UNION ALL
    SELECT id, 'status',     status::text                                                FROM clean_jira.sprints
)
INSERT INTO clean_jira.sprint_changelog (sprint_id, field_name, old_value, new_value, changed_at)
SELECT
    cf.sprint_id,
    cf.field_name,
    lk.new_value  AS old_value,
    cf.current_value AS new_value,
    now()         AS changed_at
FROM current_fields cf
LEFT JOIN last_known lk ON lk.sprint_id = cf.sprint_id AND lk.field_name = cf.field_name
WHERE cf.current_value IS DISTINCT FROM lk.new_value
RETURNING id
```

### Backward compatibility
Existing rows with `field_name='status'`, `new_value='closed'`, `old_value=NULL`:
- For closed sprints: `last_known.new_value = 'closed'`, current status = 'closed' → no new row inserted (correct)
- For active/future sprints: no prior rows → bootstrap all 5 fields (correct)

### File to modify
- **`pipelines/assets/jira/clean.py`** — update `clean_jira_sprint_changelog` function body:
  - Replace old SQL with new snapshot-diff SQL (above)
  - Update docstring to explain new behavior
  - Keep `@asset` decorator unchanged (same deps, group_name, compute_kind)

---

## Tests to update/add

### File: `tests/unit/test_jira_clean_assets_unit.py`

Replace existing `TestCleanJiraSprintChangelog` class (3 tests for old behavior) with new tests:

```
class TestCleanJiraSprintChangelog:
    test_bootstrap_inserts_all_5_fields_on_first_run
        - last_known returns empty (no prior changelog)
        - current_fields has 1 sprint with name, goal, start_date, end_date, status
        - expect 5 rows inserted (one per field)

    test_no_insertion_when_values_unchanged
        - last_known returns same values as current
        - expect 0 rows inserted

    test_detects_name_change
        - last_known has name='Sprint 1', current has name='Sprint 1 (Renamed)'
        - expect 1 row inserted: field_name='name', old_value='Sprint 1', new_value='Sprint 1 (Renamed)'

    test_detects_date_shift
        - last_known has end_date='2026-03-21', current has end_date='2026-03-28'
        - expect 1 row: field_name='end_date'

    test_handles_null_goal
        - sprint with goal=NULL both times → no row inserted (NULL IS NOT DISTINCT FROM NULL)
        - sprint with goal=NULL then 'New Goal' → 1 row inserted

    test_multiple_sprints_multiple_changes
        - 3 sprints, 2 have changes → correct count inserted

    test_sql_tracks_five_sprint_fields
        - inspect.getsource(_asset_fn(clean.clean_jira_sprint_changelog))
        - assert all 5 field names present: name, goal, start_date, end_date, status
```

Note: mock pattern must use `_asset_fn()` wrapper (same as Phase 3 tests for release_changelog).

---

## Execution order

1. Create `db/migrations/add_external_id_indexes.sql` (no tests needed - pure DDL)
2. Update `clean_jira_sprint_changelog` in `clean.py` (SQL + docstring)
3. Update tests in `test_jira_clean_assets_unit.py`
4. Run: `uv run pytest tests/unit/test_jira_clean_assets_unit.py tests/unit/test_jira_clean.py -x -q`
5. All tests must pass before finishing

## Pre-commit compliance
- SQL in f-strings: add `# noqa: S608` on CLOSING `"""` line (NOT opening)
- No new `except: pass` patterns needed
- Run black + ruff auto-fix if pre-commit fails

## Commit
After tests pass, create single commit on branch `fix/jira-pipeline-clean-layer-integrity`:
```
feat: add external_id indexes and upgrade sprint_changelog to snapshot-diff
```
