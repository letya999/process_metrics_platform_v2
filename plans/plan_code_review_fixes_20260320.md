# Plan: Code Review Fixes — Hardcore Review Findings
**Date**: 2026-03-20
**Based on**: hardcore-reviewer system scan (14 findings, F-001 to F-014)
**Consulted**: postgresql-optimization skill, dagster-expert skill, agent.md
**Scope**: pipelines/, db/, app/api/

---

## Context

Hardcore review found 14 issues across 4 severity levels. Two architecture-level themes dominate:
1. **Incomplete migration** from per-metric fact tables to generic `fact_values` store — legacy tables not dropped, API still queries old schemas, metadata strings stale
2. **Code quality** — silent error swallowing, duplicated helpers, dead functions, non-atomic writes, cartesian join performance, SQL injection in `write_table`

All changes must follow agent.md: pragmatic monolith, no new patterns without cause, prefer editing existing files.

---

## GROUP A: Database / Schema Changes

### A1 — New migration: `0023_add_calculation_settings.py`
**File**: `db/migrations/versions/0023_add_calculation_settings.py`
**Action**: CREATE

Create table `metrics.calculation_settings`:
```
id UUID PK DEFAULT gen_random_uuid()
project_id UUID NULLABLE FK → clean_jira.projects ON DELETE CASCADE
target_calculation_id UUID NOT NULL FK → metrics.calculations ON DELETE CASCADE
settings_type TEXT NOT NULL  -- e.g. 'flow_efficiency_columns', 'ttm_epic_path'
settings_json JSONB NOT NULL DEFAULT '{}'
enabled BOOLEAN NOT NULL DEFAULT true
created_at TIMESTAMPTZ DEFAULT now()
updated_at TIMESTAMPTZ DEFAULT now()
```
Indexes:
- `idx_calc_settings_project` on (project_id)
- `idx_calc_settings_calc` on (target_calculation_id)
- Unique partial: (project_id, target_calculation_id, settings_type) WHERE project_id IS NOT NULL
- Unique partial: (target_calculation_id, settings_type) WHERE project_id IS NULL

### A2 — New migration: `0024_add_fact_values_columns.py`
**File**: `db/migrations/versions/0024_add_fact_values_columns.py`
**Action**: CREATE

Two new nullable columns in `metrics.fact_values`:
1. `settings_id UUID NULLABLE FK → metrics.calculation_settings ON DELETE SET NULL`
2. `context_json JSONB NULLABLE`

Then DROP and RECREATE `metrics.v_facts` to include both new columns:
- `fv.settings_id`
- `fv.context_json`
- Add `LEFT JOIN metrics.calculation_settings cs ON fv.settings_id = cs.id`
- Expose `cs.settings_type AS calc_settings_type`, `cs.settings_json AS calc_settings_json`

Add GIN index: `CREATE INDEX idx_fact_values_context_gin ON metrics.fact_values USING gin(context_json)` WHERE context_json IS NOT NULL.

Also update `db/views/metrics.sql` to reflect the new v_facts definition.

### A3 — New migration: `0025_drop_legacy_fact_tables.py`
**File**: `db/migrations/versions/0025_drop_legacy_fact_tables.py`
**Action**: CREATE

Drop legacy tables in dependency-safe order (CASCADE handles FK constraints):
```sql
-- Views that depend on legacy tables first
DROP VIEW IF EXISTS metrics.mv_velocity CASCADE;
DROP VIEW IF EXISTS metrics.mv_lead_time CASCADE;
DROP VIEW IF EXISTS metrics.mv_throughput CASCADE;

-- Legacy wide fact tables (created in 0011, not dropped in 0014)
DROP TABLE IF EXISTS metrics.fact_velocity CASCADE;
DROP TABLE IF EXISTS metrics.fact_velocity_slice CASCADE;
DROP TABLE IF EXISTS metrics.fact_lead_time CASCADE;

-- Pro metrics tables (created in 0013, dropped in 0014 but some survive)
DROP TABLE IF EXISTS metrics.fact_work_item_aging CASCADE;
DROP TABLE IF EXISTS metrics.fact_flow_efficiency CASCADE;
DROP TABLE IF EXISTS metrics.fact_control_chart CASCADE;
DROP TABLE IF EXISTS metrics.fact_lead_time_trend CASCADE;

-- Slice tables from 0015 (never cleaned up)
DROP TABLE IF EXISTS metrics.fact_velocity_slices CASCADE;
DROP TABLE IF EXISTS metrics.fact_throughput_slices CASCADE;
DROP TABLE IF EXISTS metrics.fact_backlog_growth_slices CASCADE;
DROP TABLE IF EXISTS metrics.fact_lead_time_slices CASCADE;
DROP TABLE IF EXISTS metrics.fact_time_to_market_slices CASCADE;
DROP TABLE IF EXISTS metrics.fact_flow_efficiency_slices CASCADE;
DROP TABLE IF EXISTS metrics.fact_work_item_aging_slices CASCADE;

-- Old slice rules table superseded by metrics.slice_rules (0018)
DROP TABLE IF EXISTS metrics.metric_slice_rules CASCADE;
```

Note on CASCADE: PostgreSQL CASCADE on DROP TABLE only removes dependent objects (views, FK constraints from OTHER tables pointing here). It does NOT cascade to referenced tables (FK targets). No data loss risk from CASCADE here since these tables have no downstream dependents in the new schema.

downgrade(): raise NotImplementedError — intentional, no rollback to legacy tables.

---

## GROUP B: Infrastructure / Utilities

### B1 — Fix non-atomic write in `polars_db.py` (F-013)
**File**: `pipelines/utils/polars_db.py`
**Action**: MODIFY `write_fact_values`

Current problem: DELETE in `engine.begin()` (committed), then INSERT in separate connection. If INSERT fails, data is gone.

Fix using PostgreSQL staging table pattern (Dagster-expert + PostgreSQL skill recommendation):
```
1. Create temp table: CREATE TEMP TABLE _fact_values_stage (LIKE metrics.fact_values INCLUDING DEFAULTS)
2. INSERT new rows into _fact_values_stage via write_database/pandas
3. In a SINGLE engine.begin() transaction:
   a. DELETE FROM metrics.fact_values WHERE metric_id=ANY(...) AND project_agg_id=ANY(...) AND time_id BETWEEN...
   b. INSERT INTO metrics.fact_values SELECT * FROM _fact_values_stage
4. DROP TEMP TABLE (auto-dropped at session end anyway)
```
All steps 3a+3b in ONE `with engine.begin()` block = atomic. If either fails, full rollback.

### B2 — Fix SQL injection in `write_table` TRUNCATE (F-011)
**File**: `pipelines/utils/polars_db.py`
**Action**: MODIFY `write_table`

Replace:
```python
text(f"TRUNCATE TABLE {schema}.{table} RESTART IDENTITY CASCADE")
```
With properly quoted identifiers using SQLAlchemy's `quoted_name`:
```python
from sqlalchemy.sql.elements import quoted_name
schema_q = quoted_name(schema, quote=True)
table_q = quoted_name(table, quote=True)
text(f"TRUNCATE TABLE {schema_q}.{table_q} RESTART IDENTITY CASCADE")
```

### B3 — Fix stale process-level cache in `metric_registry.py` (F-010)
**File**: `pipelines/utils/metric_registry.py`
**Action**: MODIFY

Add TTL-based expiration to `_CACHE`. Use `time.time()` timestamps:
- Store entries as `{"value": ..., "expires_at": time.time() + TTL}`
- TTL = 300 seconds (5 minutes) for all keys
- In each getter: check `expires_at`, if expired treat as cache miss and re-query
- `clear_cache()` stays as-is for tests

This follows the "minimal change" principle from agent.md — no new dependencies, pure stdlib solution.

### B4 — Extract duplicated helpers to `commitment_resolver.py` (F-006)
**File**: `pipelines/calculations/commitment_resolver.py` — ADD two functions
**File**: `pipelines/assets/metrics/velocity.py` — REMOVE local `_load_commitment_rules`, `_resolve_rule_from_cache`, import from `commitment_resolver`
**File**: `pipelines/assets/metrics/lead_time.py` — SAME removal and import

Move `_load_commitment_rules(engine, calc_code)` and `_resolve_rule_from_cache(rules, project_id, board_id)` into `commitment_resolver.py` as public functions `load_commitment_rules_for_calc` and `resolve_rule_from_cache`. Keep the `logger.warning` on exception (already there in velocity.py, must be preserved in lead_time.py too — F-005 fix).

### B5 — Fix silent exception swallowing in lead_time asset (F-005)
**File**: `pipelines/assets/metrics/lead_time.py`
**Action**: MODIFY

Check if `_load_commitment_rules` and `_resolve_rule_from_cache` in lead_time.py have the same `logger.warning` as velocity.py. Velocity.py already has the warning. Lead_time.py may have bare `except Exception: return []`. Add `logger.warning(...)` to any bare catches in lead_time.py to match the pattern in velocity.py.

---

## GROUP C: Calculation Logic

### C1 — Unify "done status" resolution (F-007)
**File**: `pipelines/calculations/commitment_resolver.py` — ADD `get_done_column_ids(board_columns_df)`
**File**: `pipelines/calculations/throughput.py` — MODIFY `_get_done_status_ids` to call shared function
**File**: `pipelines/calculations/time_to_market.py` — MODIFY `_get_done_status_ids` to call shared function

The unified function uses the velocity.py approach (position-based: rightmost column), not name-matching heuristic. This is the most correct resolution per the review. throughput and TTM currently use name-containing("done") which fails for boards with custom column names.

New shared function `get_done_column_ids(board_columns_df: pl.DataFrame) -> list[str]`:
1. Try rightmost column by position (GROUP BY board_id, take max position)
2. Fallback: name contains "done|готово|closed|resolved|completed"
3. Return list of status_ids

### C2 — Replace Cartesian join with join_asof in backlog_growth and CFD (F-008)
**File**: `pipelines/calculations/backlog_growth.py` — MODIFY `_calculate_issue_status_on_dates`
**File**: `pipelines/calculations/cumulative_flow.py` — MODIFY equivalent function

Current code: `issues_df.join(date_range, how="cross")` → 900K+ rows for 10K issues × 90 days.

Replace with Polars `join_asof` (forward-fill pattern):
```
1. Sort status_changelog by (issue_id, changed_at)
2. For each issue, generate status intervals: (issue_id, status_id, valid_from, valid_to)
   - valid_from = changed_at of each row
   - valid_to = changed_at of next row (or today)
3. join_asof date_range to status intervals on date >= valid_from, per issue_id
```
This is O(N log N) sort + O(N+D) merge vs O(N*D) cartesian. For 10K issues × 90 days: ~900K rows → ~40K rows in changelog.

Polars join_asof signature: `date_range.join_asof(status_intervals, left_on="date", right_on="valid_from", by="issue_id", strategy="backward")`

---

## GROUP D: Dead Code Removal

### D1 — Remove/deprecate dead utility modules (F-002)
**File**: `pipelines/utils/metrics.py` — DELETE or move to `pipelines/utils/_deprecated/metrics.py`
**File**: `pipelines/utils/transformations.py` — DELETE or move to `pipelines/utils/_deprecated/transformations.py`

These modules contain 469 lines of dict-based calculation functions never called from production assets. They conflict with the canonical Polars-based approach.

Before deleting: verify with grep that no production imports exist (test imports only). If tests reference them, move to `_deprecated/` and update test imports.

### D2 — Remove dead calculation functions (F-003)
**Files**: `pipelines/calculations/lead_time.py`, `velocity.py`, `backlog_growth.py`, `cumulative_flow.py`, `time_to_market.py`
**Action**: DELETE or comment with `# DEPRECATED — not called from any asset`

Specific functions to remove:
- `lead_time.py`: `calculate_histogram_bins`, `calculate_histogram_bins_slice`, `calculate_lead_time_slice`, `calculate_lead_time_facts`
- `velocity.py`: `calculate_velocity_slice_by_issue_type`
- `backlog_growth.py`: `calculate_backlog_growth_trends`, `calculate_backlog_distribution`, `calculate_age_distribution`
- `cumulative_flow.py`: `calculate_cfd_aggregates`
- `time_to_market.py`: `calculate_ttm_aggregates`, `calculate_release_cadence`

Update unit tests that test these functions to either remove or move to `tests/_deprecated/`.

### D3 — Remove dead `write_table` function (F-012)
**File**: `pipelines/utils/polars_db.py`
**Action**: DELETE `write_table` function (lines 68-125)

This function is never called from production code. It uses TRUNCATE+INSERT non-atomically (same problem as write_fact_values) and has the SQL injection issue. Removing it eliminates both risks. The only callers are in tests — update those tests or remove them.

---

## GROUP E: API Layer Fix

### E1 — Fix broken API endpoint queries (F-001, HIGHEST PRIORITY)
**File**: `app/api/metrics.py`
**Action**: MODIFY three endpoint handlers

The API queries mv_lead_time, mv_velocity, mv_throughput with column names from the pre-0018 era. Views were rewritten post-0019. Every API call returns empty results silently.

For each endpoint, update the SQL query to use columns that actually exist in the current view definitions (from `db/views/metrics.sql`):

**`/metrics/lead-time`**: Query `metrics.v_facts` WHERE metric_code='cycle_time' (or 'lead_time' until rename). Columns: `project_key`, `entity_id AS issue_key`, `value AS lead_time_days`, `event_start_at`, `event_end_at`, `calc_code`, `full_date`

**`/metrics/velocity`**: Query `metrics.mv_velocity` or `metrics.v_facts` WHERE metric_code='velocity'. Columns: `project_key`, `entity_id AS sprint_id`, `planned_story_points`, `completed_story_points`, `planned_issues`, `completed_issues`, `full_date`

**`/metrics/throughput`**: Query `metrics.v_facts` WHERE metric_code='throughput'. Columns: `project_key`, `full_date AS week_start_date`, `value AS issues_completed`

Also remove the silent `except Exception: pass/return []` error suppression that hides schema mismatches. Replace with proper logging:
```python
except Exception as exc:
    logger.error("Metrics query failed: %s", exc)
    raise  # or return proper HTTP 500
```

### E2 — Fix stale metadata strings in refresh.py (F-009)
**File**: `pipelines/assets/metrics/refresh.py`
**Action**: MODIFY return dictionaries

Change:
- `"table": "fact_lead_time"` → `"table": "fact_values"` (or `"view": "v_facts"`)
- `"table": "fact_velocity"` → `"table": "fact_values"`
- `"source": "fact_lead_time"` → `"source": "fact_values"`

---

## Execution Order

Run in this order to avoid dependency issues:

```
1. A3 (drop legacy tables) — must run before B1/B4 to avoid confusion
   Note: check if any code still writes to legacy tables before dropping.
   Grep: grep -r "fact_velocity\|fact_lead_time\|fact_work_item_aging" pipelines/assets/
   If found: fix writers first, then drop tables.

2. A1 (calculation_settings table)
3. A2 (fact_values new columns + v_facts rebuild)

4. B4 (extract commitment helpers — pure refactor, no behavior change)
5. B5 (fix silent exceptions in lead_time.py)
6. B1 (atomic write — critical data integrity fix)
7. B2 (SQL injection fix in write_table — or just do D3 first)
8. B3 (TTL cache)

9. C1 (unify done status resolution)
10. C2 (replace cartesian join — most complex change, do last in group C)

11. D3 (delete write_table) — after B2 to remove the injected code entirely
12. D1 (delete dead utils modules)
13. D2 (delete dead calculation functions)

14. E1 (fix API queries — highest user-visible impact)
15. E2 (fix metadata strings)
```

---

## Files to Create
- `db/migrations/versions/0023_add_calculation_settings.py`
- `db/migrations/versions/0024_add_fact_values_columns.py`
- `db/migrations/versions/0025_drop_legacy_fact_tables.py`

## Files to Modify
- `pipelines/utils/polars_db.py` (B1, B2, D3)
- `pipelines/utils/metric_registry.py` (B3)
- `pipelines/calculations/commitment_resolver.py` (B4, C1)
- `pipelines/assets/metrics/velocity.py` (B4)
- `pipelines/assets/metrics/lead_time.py` (B4, B5)
- `pipelines/assets/metrics/refresh.py` (E2)
- `pipelines/calculations/throughput.py` (C1)
- `pipelines/calculations/time_to_market.py` (C1)
- `pipelines/calculations/backlog_growth.py` (C2)
- `pipelines/calculations/cumulative_flow.py` (C2)
- `app/api/metrics.py` (E1)
- `db/views/metrics.sql` (A2)

## Files to Delete
- `pipelines/utils/metrics.py` (D1) — or move to `_deprecated/`
- `pipelines/utils/transformations.py` (D1) — or move to `_deprecated/`

## Files to Partially Delete (functions removed)
- `pipelines/calculations/lead_time.py` (D2)
- `pipelines/calculations/velocity.py` (D2)
- `pipelines/calculations/backlog_growth.py` (D2)
- `pipelines/calculations/cumulative_flow.py` (D2)
- `pipelines/calculations/time_to_market.py` (D2)

---

## Validation Steps (after implementation)

1. `make migrate` — apply all three new migrations without error
2. `make test` — full test suite must pass (update tests for dead code removal)
3. `make lint` — no new lint errors
4. Manual: `curl localhost:8000/api/metrics/velocity` — must return non-empty JSON for a project with data
5. Manual: `curl localhost:8000/api/metrics/lead-time` — same
6. Dagster: materialize velocity asset for one project, verify rows in `metrics.fact_values`
7. `psql -c "\dt metrics.*"` — legacy tables should NOT appear in listing
8. Stress test backlog_growth with 5K+ issues: runtime should be < 30s (was potentially minutes)
