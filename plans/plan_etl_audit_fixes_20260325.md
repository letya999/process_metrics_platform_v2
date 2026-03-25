# ETL Audit Fixes — Full Implementation Plan
**Date:** 2026-03-25
**Scope:** All C/H/M issues from the hardcore ETL audit

---

## CONTEXT NOTES (read before coding)

- `metrics.units` table queried by `resolve_unit_field()` in `pipelines/utils/metric_registry.py:98-133`. Use `unit_code="story_points"` per project to get SP field key ID. This is THE mechanism for SP field resolution — no hardcode.
- `metrics.calculation_settings` table: `project_id` (nullable = global), `target_calculation_id`, `settings_type TEXT`, `settings_json JSONB`, `enabled BOOL`.
- The `SmartSlicer._schema_cache` attribute is initialized as `None` but never populated — a simple bug.
- `write_fact_values()` already has optional advisory lock via env var `FACT_VALUES_USE_ADVISORY_LOCK`.
- `clean_jira.issue_statuses` has `project_id NOT NULL` — statuses are project-scoped in DB. The C-2 fix is ONLY the missing `deps` declaration (no schema change).
- Sprint health `calculate_base_facts` iterates per sprint to get board-specific `done_ids`. The loop is acceptable IF we pre-group by board_id. Investigate and optimize only if clearly safe.

---

## FILES TO CREATE

### 1. `techdebt.md` (project root)

Create file with the following tech debt items:
```markdown
# Tech Debt

## TD-001: Incremental clean layer (C-6)
**Status:** Known / Not Started
All clean layer assets perform full re-scan of `raw_jira.*` on every run.
No watermark, no dlt `_dlt_load_id` range filter, no `WHERE updated_at > last_run_at`.
**Risk:** Runtime scales linearly with data. Hourly schedule breaks beyond ~50k issues.
**Resolution:** Implement per-asset high-watermark using `_dlt_load_id` or `fields__updated`.

## TD-002: Single-transaction-per-asset strategy (Architecture)
**Status:** Known / Not Started
Two conflicting patterns in codebase:
- `issues.py` — single commit at end (atomic)
- `supplementary.py` — two separate commits (partial write possible)
**Resolution:** Standardize: one `engine.begin()` (auto-commit on success) per asset. Never call `conn.commit()` manually except after deliberate checkpoint pattern.

## TD-003: Clean layer parallel run safety (C-3 partial)
**Status:** Partially fixed (TRUNCATE → DELETE in single tx)
The hourly metrics refresh job runs independently of the clean layer job. If clean layer
is mid-run, metrics compute on partially updated data.
**Resolution:** Add Dagster sensor that delays metrics refresh until clean layer finishes.
```

### 2. `db/migrations/versions/0029_seed_flow_status_categories.py`

New Alembic migration. `revision = "0029"`, `down_revision = "0028_add_ttm_calculation_settings"`.

Upgrade function:
1. Look up the `flow_efficiency` calculation ID from `metrics.calculations` where `calc_code = 'flow_efficiency_pct'` (or whatever the actual calc_code is — query it dynamically).
2. Insert ONE global `calculation_settings` row:
   - `project_id = NULL` (global default)
   - `target_calculation_id` = looked up flow_efficiency calc id
   - `settings_type = 'status_categories'`
   - `settings_json = '{"active_categories": ["in_progress"], "wait_categories": ["to_do"], "end_categories": ["done"]}'`
   - `enabled = true`
3. Use `INSERT ... ON CONFLICT DO NOTHING` so it's idempotent.

Downgrade: `DELETE FROM metrics.calculation_settings WHERE settings_type = 'status_categories' AND project_id IS NULL`.

### 3. `db/migrations/versions/0030_create_metrics_units_table.py`

Check if `metrics.units` table exists. If NOT, create it:
```sql
CREATE TABLE metrics.units (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES clean_jira.projects(id) ON DELETE CASCADE,
    unit_code TEXT NOT NULL,
    source_field_id UUID REFERENCES clean_jira.field_keys(id) ON DELETE SET NULL,
    source_entity TEXT NOT NULL DEFAULT 'field_values',
    label TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX idx_units_project_code ON metrics.units (project_id, unit_code)
    WHERE project_id IS NOT NULL;
CREATE UNIQUE INDEX idx_units_global_code ON metrics.units (unit_code)
    WHERE project_id IS NULL;
```
Then insert a placeholder global default:
```sql
INSERT INTO metrics.units (project_id, unit_code, source_field_id, source_entity, label)
VALUES (NULL, 'story_points', NULL, 'field_values', 'Story Points')
ON CONFLICT DO NOTHING;
```
NOTE: `source_field_id` is NULL in the seed — it must be set per-project via admin UI or migration once actual field_keys are populated. The code handles `None` return from `resolve_unit_field` gracefully (skip SP-dependent calculations with a warning).

If `metrics.units` already exists, skip table creation but ensure the global seed row exists.

Downgrade: `DROP TABLE IF EXISTS metrics.units`.

### 4. `pipelines/utils/constants.py`

New file:
```python
"""Project-wide constants for pipeline configuration.

Defines stable identifiers that are known ahead of time but may vary across
Jira instances. Prefer configuration (metrics.units, calculation_settings) over
these constants — use them only as last-resort fallbacks with explicit warnings.
"""

# Jira custom field IDs commonly used for sprint assignment.
# dlt generates table names like raw_jira.issues__fields__{SPRINT_FIELD_ID}.
# Override via JIRA_SPRINT_FIELD_ID env var or detect at runtime via _utils.py.
SPRINT_FIELD_ID_CANDIDATES = [
    "customfield_10020",  # Most common Jira Cloud default
    "customfield_10021",  # Some older instances
]
SPRINT_FIELD_ID_DEFAULT = "customfield_10020"

# Story points field — used as fallback when metrics.units is not seeded.
# DEPRECATED: Prefer resolve_unit_field(engine, project_id, "story_points").
STORY_POINTS_FIELD_CANDIDATES = [
    "customfield_10036",
    "customfield_10016",
    "story_points",
]
```

---

## FILES TO MODIFY

### A. `pipelines/assets/metrics/flow_efficiency.py` — C-1

**Current bug:** lines 80-88 use `"indeterminate"` and `"todo"` instead of `"in_progress"` and `"to_do"` from the DB enum.

**Fix:** Replace the hardcoded category filter with `calculation_settings` lookup.

At the top of the asset function, after loading `issue_statuses_df`, add:
```python
# Load flow status category settings from calculation_settings
settings_df = read_table(
    engine,
    "SELECT * FROM metrics.calculation_settings WHERE target_calculation_id = :calc_id AND enabled = true",
    params={"calc_id": calc_id},  # calc_id = get_calculation_id(engine, "flow_efficiency_pct")
)
```

Then replace the flat `active_statuses / wait_statuses / end_statuses` lists with per-project resolution. Move the flow calculation into a per-project loop (similar to waste.py pattern):

For each `project_id` in the data:
1. Try project-specific settings: `settings_df.filter(pl.col("project_id") == project_id)`
2. Fall back to global: `settings_df.filter(pl.col("project_id").is_null())`
3. If still empty: log `context.log.warning(f"No flow_status_categories settings for project {project_id}, skipping")` and `continue` — NO hardcoded fallback.
4. From `settings_json`: read `active_categories`, `wait_categories`, `end_categories`.
5. Filter `issue_statuses_df` by `(pl.col("project_id") == project_id) & (pl.col("category").is_in(active_categories))` etc.
6. Pass resulting ID lists to `flow_logic.calculate_flow_efficiency_per_issue(...)`.

Remove the global `active_statuses / wait_statuses / end_statuses` variables entirely.

### B. `pipelines/assets/jira/clean/dimensions.py` — C-2, H-4, H-10

**C-2 fix:** In `clean_jira_issue_statuses` asset decorator (line ~229), change `deps=["raw_jira_data"]` to `deps=["raw_jira_data", "clean_jira_projects"]`. That's the only change needed. The user confirmed statuses are project-scoped in the DB; the fix is ordering only.

**H-4 fix:** In `clean_jira_issue_types`, the `has_hierarchy_level` probe at lines 84-92 does NOT call `conn.rollback()` on exception. After the `except Exception:` block, add `conn.rollback()` before setting `has_hierarchy_level = False`. This resets the connection state so the subsequent INSERT can proceed cleanly.

Full fix:
```python
try:
    conn.execute(text("SELECT fields__issuetype__hierarchy_level FROM raw_jira.issues LIMIT 1"))
    has_hierarchy_level = True
except Exception:
    conn.rollback()  # Reset aborted transaction state
    has_hierarchy_level = False
    context.log.warning("Column 'fields__issuetype__hierarchy_level' not found, falling back to ILIKE logic")
```

Also fix `ON CONFLICT DO UPDATE SET` to include `hierarchy_level = EXCLUDED.hierarchy_level` so it's updated if hierarchy info becomes available.

**H-10 fix:** In `clean_jira_field_keys` asset, replace the per-column INSERT loop with a single multi-row INSERT. Build a list of dicts `[{"project_id": ..., "external_key": ..., "name": ...}]` for all columns, then execute one `INSERT ... VALUES ... ON CONFLICT DO UPDATE` with SQLAlchemy bulk insert or a CTE-based approach.

### C. `pipelines/assets/jira/clean/sprints.py` — C-3, H-6, H-14

**C-3 fix (TRUNCATE race condition):** In `clean_jira_sprint_issues_changelog`, replace:
```python
conn.execute(text("TRUNCATE TABLE clean_jira.sprint_issues_changelog"))
```
with:
```python
conn.execute(text("DELETE FROM clean_jira.sprint_issues_changelog"))
```
Both are in the same implicit transaction (single `with engine.connect() as conn:` block with one `conn.commit()` at the end). DELETE is transactional — it holds a lock until commit, unlike TRUNCATE which releases immediately. Other concurrent readers see the old data until commit, then the new data. No zero-row window.

**H-6 fix:** Import `SPRINT_FIELD_ID_DEFAULT` and `SPRINT_FIELD_ID_CANDIDATES` from `pipelines.utils.constants`. In `_detect_sprint_field_id()` (in `_utils.py`), use the candidates list in the fallback order instead of a hardcoded string. Keep the existing detection logic but replace hardcoded `"customfield_10020"` string references with the constant.

**H-14 analysis and fix:** The `snapshot_events` CTE in `clean_jira_sprint_issues` and `clean_jira_sprint_issues_changelog` reads from `raw_jira.issues__fields__{sprint_field_id}` — this is the CURRENT sprint field, not historical. For issues that:
- Were created in Sprint A (no changelog) → moved to Sprint B (changelog entry exists) → the issue has changelog entries, so `snapshot_events` excludes it → changelog correctly shows add/remove events → CORRECT.
- Were created in Sprint A (no changelog), never moved → `snapshot_events` sees Sprint A → CORRECT.
- Were created in Sprint A (no changelog), then Sprint A was deleted/merged (possible in Jira admin) → the field shows Sprint B or NULL → `snapshot_events` would show Sprint B → INCORRECT.

The last case is an edge case that cannot be recovered without historical snapshots. Document this limitation in a code comment. NO code change for this — just add a comment explaining why the snapshot_events fallback uses current state and what the known limitation is.

### D. `pipelines/assets/jira/clean/issues.py` — C-4, H-3, H-8, H-13

**C-4 fix (silent issue drop on dimension JOIN miss):** Change INNER JOIN on `issue_types` and `issue_statuses` to LEFT JOIN. Then filter `WHERE it.id IS NOT NULL AND ist.id IS NOT NULL` — but BEFORE the INSERT, add a CTE that logs/counts dropped issues:

Actually, since we can't log per-row in SQL, the approach is:
1. Keep the LEFT JOIN.
2. Add a separate COUNT query before the INSERT to log how many issues would be dropped:
```sql
SELECT COUNT(*) FROM raw_jira.issues r
JOIN clean_jira.projects p ON ...
LEFT JOIN clean_jira.issue_types it ON ...
LEFT JOIN clean_jira.issue_statuses ist ON ...
WHERE (it.id IS NULL OR ist.id IS NULL) AND r.id IS NOT NULL
```
3. If count > 0: `context.log.warning(f"{count} issues dropped due to missing type_id or status_id in dimension tables")`
4. Keep the original INNER JOIN for the actual INSERT (so type_id/status_id remain NOT NULL) — the NOT NULL constraint is enforced by schema.
5. Add an asset check `check_raw_clean_issue_count` threshold change from 5% to something configurable, or keep at 5% but add a separate `check_issue_dimension_drops` asset check (see checks section).

**H-3 fix (bidirectional links):** In `clean_jira_issue_links`, the current CTE uses `COALESCE(outward_issue__id, inward_issue__id)` which picks only one direction. Fix:

Replace the `link_data` CTE with a UNION of both directions:
```sql
WITH link_data AS (
    -- Outward links: source → target
    SELECT
        il.type__id as type_external_id,
        r.id::text as source_external_id,
        il.outward_issue__id::text as target_external_id,
        r.fields__project__id::text as project_external_id
    FROM raw_jira.issues__fields__issuelinks il
    JOIN raw_jira.issues r ON il._dlt_parent_id = r._dlt_id
    WHERE il.type__id IS NOT NULL AND il.outward_issue__id IS NOT NULL
    UNION ALL
    -- Inward links: source → target (inward direction)
    SELECT
        il.type__id as type_external_id,
        r.id::text as source_external_id,
        il.inward_issue__id::text as target_external_id,
        r.fields__project__id::text as project_external_id
    FROM raw_jira.issues__fields__issuelinks il
    JOIN raw_jira.issues r ON il._dlt_parent_id = r._dlt_id
    WHERE il.type__id IS NOT NULL AND il.inward_issue__id IS NOT NULL
      AND il.outward_issue__id IS DISTINCT FROM il.inward_issue__id  -- avoid dup when same
)
```
The `ON CONFLICT (relation_type_id, source_issue_id, target_issue_id) DO NOTHING` handles deduplication.

**H-8 fix (unguarded timestamp cast):** In the issues UPSERT SQL, replace:
```sql
r.fields__created::timestamptz as jira_created_at,
r.fields__updated::timestamptz as jira_updated_at,
r.fields__resolutiondate::timestamptz as jira_resolved_at,
```
with:
```sql
NULLIF(trim(r.fields__created::text), '')::timestamptz as jira_created_at,
NULLIF(trim(r.fields__updated::text), '')::timestamptz as jira_updated_at,
NULLIF(trim(r.fields__resolutiondate::text), '')::timestamptz as jira_resolved_at,
```
And in the WHERE clause, add `AND r.fields__created IS NOT NULL` to exclude issues with null creation date (required field). Add `context.log.warning(...)` after counting to surface if any issues had null dates.

**H-13 fix (status changelog conflict key):** In `clean_jira_issue_status_changelog`, the current `ON CONFLICT (issue_id, to_status_id, changed_at) DO NOTHING` misses cases where `from_status_id` changes.

Change to:
```sql
ON CONFLICT (issue_id, to_status_id, changed_at) DO UPDATE SET
    from_status_id = EXCLUDED.from_status_id
WHERE issue_status_changelog.from_status_id IS DISTINCT FROM EXCLUDED.from_status_id
```
This allows updating `from_status_id` if Jira corrects it, while not updating if there's no change.

Also check if `from_status_id` is part of a UNIQUE constraint. If not, no index change needed. If the unique constraint only covers `(issue_id, to_status_id, changed_at)`, the `DO UPDATE SET` works.

### E. `pipelines/assets/jira/clean/maintenance.py` — C-5, M-2

**C-5 fix:** Replace `return {"status": "failed", "error": str(e)}` with `raise`. Let Dagster handle the error visibility. The except block should:
```python
except Exception as e:
    context.log.error(f"Error during ghost cleanup: {e}")
    raise
```

**M-2 fix (pagination safety):** In the ghost cleanup Jira API loop, track the total pages/items expected vs received. If the paginated result set is unexpectedly smaller than expected (e.g., first page had N items, then pagination stopped early with fewer total items than raw DB count), abort the cleanup and log a critical warning instead of proceeding with deletion.

Add a safety check before the DELETE loop:
```python
total_raw_issues = conn.execute(text("SELECT COUNT(*) FROM raw_jira.issues")).scalar()
if len(all_jira_ids) < total_raw_issues * 0.9:  # If we got less than 90% of what we have
    context.log.warning(
        f"Jira API returned only {len(all_jira_ids)} IDs but DB has {total_raw_issues} issues. "
        "Aborting ghost cleanup to prevent false deletions."
    )
    return {"status": "aborted_incomplete_api_response", "jira_ids": len(all_jira_ids), "db_count": total_raw_issues}
```

### F. `pipelines/assets/metrics/sprint_health.py` — H-5, H-7, H-9

**H-5/H-7 fix (SP field via units):** Replace the hardcoded SP field detection:
```python
sp_fields = field_keys_df.filter(
    (pl.col("external_key").is_in(["customfield_10036", "customfield_10016", "story_points"]))
    | (pl.col("name").str.to_lowercase().str.contains("story point"))
)
sp_field_key_id = sp_fields["id"][0] if not sp_fields.is_empty() else None
```

With per-project SP field resolution using `resolve_unit_field`:
```python
from pipelines.utils.metric_registry import resolve_unit_field

# SP field is now resolved per-project inside calculate_base_facts
# sp_field_key_id is removed from outer scope
```

Inside `calculate_base_facts`, for each project_id:
```python
unit = resolve_unit_field(engine, p_id, "story_points")
if unit:
    sp_field_key_id = unit["source_field_id"]
else:
    context.log.warning(f"No story_points unit configured for project {p_id}. SP-dependent metrics will be zero.")
    sp_field_key_id = None
```

Pass `sp_field_key_id` down to `calculate_sprint_burndown`, `calculate_sprint_scope_changes`, etc.

**H-9 fix (O(N) loop):** Investigate the `for sprint in sub_sprints.to_dicts():` loop. The per-sprint iteration exists because:
- `board_columns_df.filter(pl.col("board_id") == b_id)` — board_id lookup
- `resolve_rule_from_cache(lead_time_rules, p_id, b_id)` — rule per board

Optimization: Group sprints by `(project_id, board_id)`. For each unique `(p_id, b_id)` pair:
1. Compute `board_cols`, `rule`, `done_ids` ONCE.
2. Then filter all sprints for that board and pass the filtered DataFrame to `calculate_sprint_burndown` and `calculate_activation_velocity`.
3. Modify `calculate_sprint_burndown` and `calculate_activation_velocity` to accept a multi-sprint DataFrame and return results for all sprints.

If modifying `calculate_sprint_burndown` to accept multiple sprints is too risky (changes calculation logic), at minimum cache `board_cols` and `rule` lookups per `(p_id, b_id)` pair using a local dict to avoid repeated `filter()` calls:
```python
board_cols_cache = {}
rule_cache = {}
for sprint in sub_sprints.to_dicts():
    p_id, s_id = sprint["project_id"], sprint["id"]
    b_id = boards_df.filter(pl.col("project_id") == p_id).select("id").to_series()
    b_id = b_id[0] if not b_id.is_empty() else None
    if not b_id:
        continue
    if b_id not in board_cols_cache:
        board_cols_cache[b_id] = board_columns_df.filter(pl.col("board_id") == b_id)
    board_cols = board_cols_cache[b_id]
    ...
```
This eliminates repeated Polars filter allocations for the same board.

### G. `pipelines/assets/jira/clean/supplementary.py` — H-5, M-1, M-8, M-11

**M-1 fix (fetchall OOM):** Replace `batch_rows = conn.execute(rows_query).fetchall()` with server-side cursor streaming. Use `conn.execution_options(stream_results=True).execute(rows_query)` and iterate with `yield_per(1000)`:
```python
result = conn.execution_options(stream_results=True).execute(rows_query)
insert_data = []
for row in result.yield_per(1000):
    # ... process row ...
    if len(insert_data) >= 5000:
        conn.execute(stmt, insert_data)
        insert_data = []
# flush remainder
if insert_data:
    conn.execute(stmt, insert_data)
```
This caps in-memory usage to ~5000 rows at a time regardless of table size.

**M-8 fix (pg_temp function on pooled connection):** The `CREATE OR REPLACE FUNCTION pg_temp.safe_timestamptz` in `clean_jira_comments` uses a pg_temp function. pg_temp functions are session-scoped. When the connection returns to the pool and is reused, the temp function IS still available (same session). But if the pool creates a NEW connection, it won't have the function.

Fix: Before the INSERT that calls `pg_temp.safe_timestamptz(...)`, always run `CREATE OR REPLACE FUNCTION pg_temp.safe_timestamptz(...)` at the start of the `with engine.connect() as conn:` block. This is idempotent (OR REPLACE) and adds minimal overhead.

**M-11 fix (str(None) stored as "None"):** In the field values loop, `val_str = str(val)` on line 370 can produce `"None"` if a DB driver returns a Python `None` object. Add explicit check before `str()`:
```python
if val is None:
    continue
val_str = str(val)
if val_str in ("None", "nan", "NaN", "NULL", "null", ""):
    continue
```

**H-5 (SP field via units in supplementary):** The sprint field value extraction in supplementary.py uses `_detect_sprint_field_id(conn)` which is fine. But any SP field handling should NOT use hardcoded field names. Check if supplementary.py references any SP field directly and replace with `resolve_unit_field` if found.

### H. `pipelines/assets/jira/clean/checks.py` — H-1 test, flow_efficiency check

**H-1: Asset check for flow efficiency non-zero data:**
Add `check_flow_efficiency_non_zero` asset check targeting `calculate_flow_efficiency` asset:
```python
@asset_check(
    asset=calculate_flow_efficiency,
    description="Verify flow_efficiency_pct is not all-zero (detects wrong status category config)",
)
def check_flow_efficiency_nonzero(
    context: AssetCheckExecutionContext,
    database: DatabaseResource,
) -> AssetCheckResult:
    """Detect case where flow_efficiency_pct is 0 for ALL issues.
    This indicates status category misconfiguration (e.g. wrong category enum values).
    """
    engine = database.get_engine()
    with engine.connect() as conn:
        # Check fact_values for flow_efficiency metric
        result = conn.execute(text("""
            SELECT COUNT(*) as total, SUM(CASE WHEN value > 0 THEN 1 ELSE 0 END) as nonzero
            FROM metrics.fact_values fv
            JOIN metrics.calculations c ON c.id = fv.metric_id
            WHERE c.calc_code = 'flow_efficiency_pct'
        """)).fetchone()
    total = result[0] or 0
    nonzero = result[1] or 0
    if total == 0:
        return AssetCheckResult(passed=True, metadata={"status": "no_data"})
    nonzero_pct = (nonzero / total) * 100
    return AssetCheckResult(
        passed=nonzero_pct > 5.0,  # At least 5% of issues should have >0 flow efficiency
        metadata={"total_rows": total, "nonzero_rows": nonzero, "nonzero_pct": round(nonzero_pct, 2)},
    )
```

Also add a unit test in `tests/` for this check if a tests directory exists.

**H-1: Add a test for sprint_health SP field resolution:**
In `tests/test_sprint_health.py` (create if needed), add a test that:
1. Creates a mock engine/session
2. Calls `resolve_unit_field(mock_engine, "test_project_id", "story_points")`
3. Asserts it returns the configured field key, not a hardcoded one
4. Tests the fallback to global unit when project-specific is not set

### I. `pipelines/utils/smart_slicer.py` — M-5

**Fix: Populate `_schema_cache` on first call.**

In `_get_schema_graph()`, change:
```python
def _get_schema_graph(self, schema: str = "clean_jira") -> ...:
    inspector = inspect(self.engine)
    graph = {}
    ...
    return graph
```
To:
```python
def _get_schema_graph(self, schema: str = "clean_jira") -> ...:
    if self._schema_cache is not None:
        return self._schema_cache
    inspector = inspect(self.engine)
    graph = {}
    ...
    self._schema_cache = graph
    return graph
```

Also fix `find_target_for_column()` which calls `_get_schema_graph()` but also directly calls `inspector.get_table_names()` and `inspector.get_columns()`. These extra `inspector` calls bypass the cache. For the column checks, add a `_columns_cache: Dict[str, List[str]] = {}` dict on the instance and cache per-table column lists.

### J. `pipelines/utils/metric_registry.py` — M-9, H-11

**M-9 fix (thread safety):** Add a `threading.Lock` for `_CACHE` mutations.

Add at module level:
```python
import threading
_CACHE_LOCK = threading.Lock()
```

Wrap the TOCTOU pattern in `_get_from_cache` / `_set_in_cache` calls:
```python
def _get_from_cache(key: str) -> Optional[Any]:
    with _CACHE_LOCK:
        entry = _CACHE.get(key)
        if entry and entry["expires_at"] > time.time():
            return entry["value"]
    return None

def _set_in_cache(key: str, value: Any) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = {"value": value, "expires_at": time.time() + _TTL}
```

**H-11 fix (N connections for project_agg_id):** Add a batch lookup function:
```python
def get_project_agg_ids_batch(engine: Engine, project_ids: list[str]) -> dict[str, str]:
    """Return {project_id: project_agg_id} for all given project_ids in one query."""
    # Check cache first
    result = {}
    missing = []
    for pid in project_ids:
        cached = _get_from_cache(f"proj_agg_id_{pid}")
        if cached is not None:
            result[pid] = cached
        else:
            missing.append(pid)

    if missing:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT project_id, id FROM metrics.dim_projects WHERE project_id = ANY(CAST(:ids AS uuid[]))"),
                {"ids": missing}
            ).fetchall()
        for row in rows:
            pid, agg_id = str(row[0]), str(row[1])
            _set_in_cache(f"proj_agg_id_{pid}", agg_id)
            result[pid] = agg_id

        for pid in missing:
            if pid not in result:
                raise ValueError(f"Project ID '{pid}' not found in metrics.dim_projects.")

    return result
```

Then in all metric assets that do:
```python
project_agg_map = {pid: get_project_agg_id(engine, pid) for pid in project_ids}
```
Replace with:
```python
from pipelines.utils.metric_registry import get_project_agg_ids_batch
project_agg_map = get_project_agg_ids_batch(engine, project_ids)
```

Files to update: `velocity.py`, `sprint_health.py`, `flow_efficiency.py`, `lead_time.py`, `throughput.py`, `aging.py`, `time_to_market.py`, `waste.py` — check each one for the pattern.

### K. `pipelines/assets/jira/clean/releases.py` — M-4

**Fix (removed release issues have no record):** In `clean_jira_release_issues`, the INSERT only inserts issues where `la.action = 'added'`. Change to insert ALL final states:

Replace `WHERE la.action = 'added'` with removing the WHERE and using:
```sql
INSERT INTO clean_jira.release_issues (release_id, issue_id, is_active)
SELECT
    rel.id as release_id,
    i.id as issue_id,
    CASE WHEN la.action = 'added' THEN true ELSE false END as is_active
FROM latest_action la
...
ON CONFLICT (release_id, issue_id) DO UPDATE SET
    is_active = EXCLUDED.is_active
```
This matches the `sprint_issues` pattern (which already uses `is_active = CASE WHEN action = 'added' THEN true ELSE false END`).

### L. `pipelines/calculations/slicing_utils.py` — M-7

**Fix (missing slice_rules returns empty silently):** Change:
```python
except Exception as e:
    logger.warning(f"Could not load slice rules: {e}")
    return pl.DataFrame(...)
```
To:
```python
except Exception as e:
    if "relation" in str(e).lower() and "does not exist" in str(e).lower():
        # Schema not yet migrated — propagate as a clear error
        raise RuntimeError(
            "metrics.slice_rules table does not exist. Run: alembic upgrade head"
        ) from e
    raise
```

### M. `db/schemas/clean_jira_schema.sql` and via migration — M-6

**Add missing indexes.** Create migration `0031_add_clean_jira_indexes.py`:

```sql
-- issue_status_changelog: most frequent join pattern
CREATE INDEX IF NOT EXISTS idx_issue_status_changelog_issue_id_changed_at
    ON clean_jira.issue_status_changelog (issue_id, changed_at DESC);

-- sprint_issues_changelog: sprint history lookups
CREATE INDEX IF NOT EXISTS idx_sprint_issues_changelog_sprint_id
    ON clean_jira.sprint_issues_changelog (sprint_id, changed_at DESC);
CREATE INDEX IF NOT EXISTS idx_sprint_issues_changelog_issue_id
    ON clean_jira.sprint_issues_changelog (issue_id);

-- field_values: SP lookups by field_key_id
CREATE INDEX IF NOT EXISTS idx_field_values_field_key_id
    ON clean_jira.field_values (field_key_id);
CREATE INDEX IF NOT EXISTS idx_field_values_issue_id_field_key
    ON clean_jira.field_values (issue_id, field_key_id);

-- issues: status and type filtering
CREATE INDEX IF NOT EXISTS idx_issues_status_id
    ON clean_jira.issues (status_id);
CREATE INDEX IF NOT EXISTS idx_issues_type_id
    ON clean_jira.issues (type_id);
CREATE INDEX IF NOT EXISTS idx_issues_project_id_updated_at
    ON clean_jira.issues (project_id, jira_updated_at DESC);
```

Also add `CONCURRENTLY` where possible since these are added post-schema on live tables.

### N. `pipelines/utils/polars_db.py` — H-15

**Fix (concurrent metric writes):** The advisory lock is already implemented but opt-in. Change the default to opt-out instead of opt-in:
```python
use_advisory_lock = (
    os.getenv("FACT_VALUES_USE_ADVISORY_LOCK", "true").lower() != "false"  # default ON
)
```
Also improve the lock key to cover all metric_ids, not just the first one:
```python
if use_advisory_lock and metric_ids:
    # Hash all metric IDs together for a stable per-metric-set lock
    lock_key = "_".join(sorted(metric_ids))
    conn.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
        {"lock_key": lock_key},
    )
```

### O. `pipelines/assets/jira/clean/_utils.py` — H-6

**Fix:** Import `SPRINT_FIELD_ID_CANDIDATES` and `SPRINT_FIELD_ID_DEFAULT` from `pipelines.utils.constants`. In `_detect_sprint_field_id(conn)`, use the candidates list for detection. Replace any literal `"customfield_10020"` string with `SPRINT_FIELD_ID_DEFAULT` from constants.

### P. `pipelines/assets/jira/clean/dimensions.py` — M-10

**Fix (repeated information_schema checks):** Add a module-level or function-level cache dict for existence checks:
```python
_TABLE_EXISTS_CACHE: dict[str, bool] = {}

def _table_exists(conn, schema: str, table: str) -> bool:
    key = f"{schema}.{table}"
    if key in _TABLE_EXISTS_CACHE:
        return _TABLE_EXISTS_CACHE[key]
    result = conn.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = :schema AND table_name = :table
        )
    """), {"schema": schema, "table": table}).scalar()
    _TABLE_EXISTS_CACHE[key] = bool(result)
    return bool(result)
```

Replace all inline `information_schema.tables` checks across `dimensions.py`, `sprints.py`, `issues.py`, `supplementary.py` with calls to this utility function.

---

## EXECUTION ORDER

Gemini should implement changes in this order to avoid breaking dependencies:

1. Create `pipelines/utils/constants.py` (no deps)
2. Create `techdebt.md` (no deps)
3. Modify `pipelines/utils/metric_registry.py` (add batch function, thread lock)
4. Modify `pipelines/utils/smart_slicer.py` (cache fix)
5. Modify `pipelines/utils/polars_db.py` (advisory lock default)
6. Modify `pipelines/assets/jira/clean/_utils.py` (use constants)
7. Modify `pipelines/assets/jira/clean/dimensions.py` (C-2 deps, H-4 rollback, H-10 batch insert, M-10 cache)
8. Modify `pipelines/assets/jira/clean/issues.py` (C-4, H-3, H-8, H-13)
9. Modify `pipelines/assets/jira/clean/sprints.py` (C-3, H-6, H-14 comment)
10. Modify `pipelines/assets/jira/clean/maintenance.py` (C-5, M-2)
11. Modify `pipelines/assets/jira/clean/releases.py` (M-4)
12. Modify `pipelines/assets/jira/clean/supplementary.py` (M-1, M-8, M-11)
13. Modify `pipelines/assets/jira/clean/checks.py` (H-1 check)
14. Modify `pipelines/calculations/slicing_utils.py` (M-7)
15. Create migrations: `0029`, `0030`, `0031`
16. Modify `pipelines/assets/metrics/flow_efficiency.py` (C-1 - requires migration 0029)
17. Modify `pipelines/assets/metrics/sprint_health.py` (H-5, H-7, H-9 - requires migration 0030)

---

## IMPORTANT CONSTRAINTS

- Do NOT use `any` type in Python — use `Unknown` or specific types.
- Do NOT add Co-authored-by in commits.
- Do NOT add docstrings or comments to code you didn't change.
- Add comments ONLY where logic is non-obvious.
- English only in code, comments, commits.
- All SQL identifiers from user data must be parameterized (no f-string SQL injection).
- Exception: dynamic table names from `_detect_sprint_field_id()` must be pre-validated against a whitelist of known patterns before interpolation into SQL.
- Run `ruff check` and `ruff format` after each file change.
- Do NOT modify test files unless specifically asked (the check in H-1 is a Dagster asset_check, not a pytest test).
