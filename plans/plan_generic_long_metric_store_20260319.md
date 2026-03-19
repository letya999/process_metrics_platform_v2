# Plan: Migrate to Generic Long Metric Store
**Date:** 2026-03-19
**Branch:** feature/generic-long-metric-store (create from feature/update-metric-slicing-architecture)
**Vision:** GENERIC_LONG_METRIC_STORE_VISION.md

---

## Context & Engineering Rules (from research)

### 15 Design Questions → Engineering Rules

**R1 — Idempotent writes to fact_values:**
Use `DELETE WHERE metric_id IN (:ids) AND project_agg_id IN (:ids) AND time_id BETWEEN :start AND :end` + bulk INSERT via ADBC. NOT TRUNCATE (fact_values is shared across metrics). NOT UPSERT (slower due to conflict detection overhead on large batches).

**R2 — Polars → PostgreSQL write performance:**
Replace `df.to_pandas().to_sql(method="multi")` with `df.write_database(uri, engine="adbc")`. ADBC uses PostgreSQL COPY protocol — 10-50x faster for bulk inserts. Required package: `adbc-driver-postgresql`. Current `polars_db.write_table()` bridges through Pandas — this must be changed for fact_values writes.

**R3 — Partial failure isolation:**
Each metric asset writes within `with engine.begin() as conn` (auto-rollback on exception). Writes are scoped by `metric_id` — failed assets don't corrupt other metrics. Use savepoints for multi-step writes within one asset.

**R4 — PostgreSQL partitioning:**
Partition `fact_values` by `time_id` RANGE (quarterly or yearly). Enables partition pruning for BI queries. Partition drop = instant data cleanup. For PM-maintained system, use yearly partitions: `fact_values_2025`, `fact_values_2026`. Add `pg_partman` recommendation in docs (NOT required for MVP).

**R5 — Incremental refresh strategy per grain:**
- `grain=issue` (lead_time, ttm, aging): process issues resolved/updated in last 90 days. Full backfill available via Dagster backfill.
- `grain=week` (throughput): full refresh for rolling 13-week window (DELETE + INSERT).
- `grain=day` (cfd, backlog_growth): full refresh for rolling 90-day window.
- `grain=sprint` (velocity): full refresh for all closed sprints in last 6 months.

**R6 — Dagster asset checks:**
Add `@asset_check` after each metric asset write: (1) row count > 0, (2) no NULL values in `value`, (3) `time_id` within expected range, (4) no duplicate `(metric_id, project_agg_id, time_id, entity_id, slice_rule_id)` tuples.

**R7 — fact_values indexes:**
```sql
-- Primary: covers 90% of Metabase queries
CREATE INDEX idx_fact_values_main
  ON metrics.fact_values (metric_id, project_agg_id, time_id)
  INCLUDE (value, slice_value, entity_id, entity_type);

-- Cross-metric project dashboard queries
CREATE INDEX idx_fact_values_project_time
  ON metrics.fact_values (project_agg_id, time_id)
  INCLUDE (value, metric_id);

-- Partial: base metrics only (no slice) - most common BI filter
CREATE INDEX idx_fact_values_base
  ON metrics.fact_values (metric_id, project_agg_id, time_id)
  WHERE slice_rule_id IS NULL;

-- Drill-down by entity
CREATE INDEX idx_fact_values_entity
  ON metrics.fact_values (entity_type, entity_id)
  WHERE entity_id IS NOT NULL;
```

**R8 — NULL vs 0 semantics:**
Never write NULL to `value`. Skip the row if no data. Write `value = 0.0` only when an event occurred and the result was genuinely zero (e.g., sprint started but 0 issues completed). Absence of a row = no data for that period.

**R9 — Polars LazyFrame pattern:**
All production calculation paths must use `pl.LazyFrame` with `.collect()` at the end. Use `pl.col("x").drop_nulls()` before groupby on nullable columns. Avoid `.over()` on high-cardinality columns.

**R10 — Snapshot metric idempotency (aging, backlog_size):**
Daily snapshots: `DELETE WHERE metric_id = :id AND time_id = :today AND project_agg_id IN (:ids)` then INSERT. Same-day reruns are idempotent. Historical recalculation uses Dagster daily partition backfill.

**R11 — Dagster partition definitions:**
- `DailyPartitionsDefinition` → cfd, backlog_growth, aging
- `WeeklyPartitionsDefinition` → throughput
- `DynamicPartitionsDefinition` (sprint IDs) → velocity (future, MVP uses unpartitioned)
- Non-partitioned with incremental window → lead_time, ttm, flow_efficiency (MVP)

**R12 — entity_id as TEXT:**
`entity_type TEXT + entity_id TEXT` is correct (UUID as string, issue keys, week dates). Add composite index `(entity_type, entity_id)` for drill-down. UUID columns cast via `entity_id::uuid` only at query time.

**R13 — Database resource configuration:**
Single synchronous SQLAlchemy engine per Dagster worker: `pool_size=5, max_overflow=10, pool_pre_ping=True, pool_recycle=3600`. ADBC requires separate URI-based connection (not SQLAlchemy). Keep ADBC writes in try/finally with explicit close.

**R14 — value column type: DOUBLE PRECISION not NUMERIC:**
`DOUBLE PRECISION` (float8) for all metric values. Metrics (days, counts, points) don't need arbitrary precision. float8 is 2-5x faster in analytics aggregations. Only financial systems need NUMERIC.

**R15 — Slice resolution: no N+1:**
Load ALL active slice_rules for all projects in ONE query at asset startup. Pass pre-loaded `rules_df` to `apply_slicing()`. Never fetch per-project inside the slicing loop. Current `get_slice_rules()` is called once per asset — correct pattern to preserve.

---

## Architecture Changes Required

### Critical Issues Found in Current Code

1. **`pipelines/utils/polars_db.py`**: `write_table()` uses Pandas bridge + `to_sql(method="multi")` — must add ADBC-based `write_fact_values()` function
2. **`pipelines/calculations/lead_time.py`**: `identify_commitment_points()` uses hardcoded string matching (`"in progress"`, `"done"`, `"в работе"`, `"готово"`) — must read from `commitment_rules` table
3. **`pipelines/calculations/slicing_utils.py`**: reads from `metrics.metric_slice_rules` (old table name), fragile `filter_condition` string parser — must update to `metrics.slice_rules`
4. **`pipelines/calculations/velocity.py`**: story points read directly from `field_values` by hardcoded field name — must use `units` table for resolution
5. **`db/migrations/versions/e17a9cb848b6_*`**: last migration FKs to `metric_slice_rules` — new schema has `slice_rules`
6. **All metric assets**: write to separate `fact_velocity`, `fact_lead_time`, etc. — must write to `fact_values`
7. **`metrics.metric_slice_rules`**: old table name — must rename to `metrics.slice_rules`

---

## Implementation Plan

### Phase 0: Schema — New Tables Migration

**Task 0.1 — Migration: create new configuration and dimension tables**

File to create: `db/migrations/versions/0018_add_generic_metric_store_foundation.py`

Create these tables in the `metrics` schema:

```
metrics.definitions:
  id UUID PK DEFAULT gen_random_uuid()
  metric_code TEXT UNIQUE NOT NULL
  created_at TIMESTAMPTZ DEFAULT now()
  updated_at TIMESTAMPTZ DEFAULT now()

metrics.grains:
  id UUID PK DEFAULT gen_random_uuid()
  grain_code TEXT UNIQUE NOT NULL  -- issue, sprint, week, day, release
  description TEXT
  created_at TIMESTAMPTZ DEFAULT now()

metrics.units:
  id UUID PK DEFAULT gen_random_uuid()
  project_id UUID REFERENCES clean_jira.projects(id) ON DELETE CASCADE
  unit_code TEXT NOT NULL  -- story_points, issues, days, hours, percent
  display_symbol TEXT NOT NULL  -- SP, items, d, h, %
  source_field_id UUID REFERENCES clean_jira.field_keys(id) ON DELETE SET NULL
  source_entity TEXT  -- 'clean_jira.issues', 'clean_jira.sprints'
  created_at TIMESTAMPTZ DEFAULT now()
  updated_at TIMESTAMPTZ DEFAULT now()
  UNIQUE(project_id, unit_code)  -- nullable unique: use partial index below
  -- Partial unique: UNIQUE(unit_code) WHERE project_id IS NULL
  -- Partial unique: UNIQUE(project_id, unit_code) WHERE project_id IS NOT NULL

metrics.calculations:
  id UUID PK DEFAULT gen_random_uuid()
  definition_id UUID NOT NULL REFERENCES metrics.definitions(id) ON DELETE CASCADE
  calc_code TEXT UNIQUE NOT NULL
  grain_id UUID NOT NULL REFERENCES metrics.grains(id)
  unit_code TEXT NOT NULL
  uses_commitment_points BOOLEAN DEFAULT false
  created_at TIMESTAMPTZ DEFAULT now()
  updated_at TIMESTAMPTZ DEFAULT now()

metrics.slice_rules:
  id UUID PK DEFAULT gen_random_uuid()
  project_id UUID REFERENCES clean_jira.projects(id) ON DELETE CASCADE
  rule_name TEXT NOT NULL
  target_definition_id UUID REFERENCES metrics.definitions(id) ON DELETE SET NULL
  target_definition_name TEXT
  source_table TEXT NOT NULL
  group_by_source_column TEXT NOT NULL
  enabled BOOLEAN DEFAULT true
  created_at TIMESTAMPTZ DEFAULT now()
  updated_at TIMESTAMPTZ DEFAULT now()

metrics.commitment_rules:
  id UUID PK DEFAULT gen_random_uuid()
  project_id UUID REFERENCES clean_jira.projects(id) ON DELETE CASCADE
  board_id UUID REFERENCES clean_jira.boards(id) ON DELETE CASCADE
  target_calculation_id UUID NOT NULL REFERENCES metrics.calculations(id) ON DELETE CASCADE
  target_calculation_name TEXT NOT NULL
  start_column_id UUID NOT NULL REFERENCES clean_jira.board_columns(id) ON DELETE CASCADE
  end_column_id UUID NOT NULL REFERENCES clean_jira.board_columns(id) ON DELETE CASCADE
  start_column_name_snapshot TEXT NOT NULL
  end_column_name_snapshot TEXT NOT NULL
  created_at TIMESTAMPTZ DEFAULT now()
  updated_at TIMESTAMPTZ DEFAULT now()

metrics.dim_projects:
  id UUID PK DEFAULT gen_random_uuid()
  project_id UUID NOT NULL REFERENCES clean_jira.projects(id) ON DELETE CASCADE
  project_key TEXT NOT NULL
  created_at TIMESTAMPTZ DEFAULT now()
  updated_at TIMESTAMPTZ DEFAULT now()
  UNIQUE(project_id)

metrics.dim_dates:
  time_id INT PRIMARY KEY  -- YYYYMMDD format e.g. 20260318
  full_date DATE NOT NULL UNIQUE
  week_num INT NOT NULL
  month_num INT NOT NULL
  quarter INT NOT NULL
  year INT NOT NULL
```

Acceptance criteria:
- Migration applies cleanly via `make migrate`
- All 7 tables created with correct constraints and FK references
- `make migrate` downgrade works
- No errors on `SELECT * FROM metrics.definitions LIMIT 1`

---

**Task 0.2 — Migration: create fact_values table with indexes**

File to create: `db/migrations/versions/0019_add_fact_values_and_view.py`

```
metrics.fact_values:
  id UUID PK DEFAULT gen_random_uuid()
  metric_id UUID NOT NULL REFERENCES metrics.calculations(id)
  project_agg_id UUID NOT NULL REFERENCES metrics.dim_projects(id)
  time_id INT NOT NULL REFERENCES metrics.dim_dates(time_id)
  value DOUBLE PRECISION NOT NULL
  entity_type TEXT  -- 'issue', 'sprint', 'week', 'board_column', 'release'
  entity_id TEXT    -- issue key, sprint UUID as text, week date, column UUID as text
  event_start_at TIMESTAMPTZ  -- for flow metrics: commitment zone entry
  event_end_at TIMESTAMPTZ    -- for flow metrics: commitment zone exit
  slice_rule_id UUID REFERENCES metrics.slice_rules(id) ON DELETE SET NULL
  slice_value TEXT
  commitment_rule_id UUID REFERENCES metrics.commitment_rules(id) ON DELETE SET NULL
  created_at TIMESTAMPTZ DEFAULT now()
  updated_at TIMESTAMPTZ DEFAULT now()

Create indexes:
  idx_fact_values_main: (metric_id, project_agg_id, time_id) INCLUDE (value, slice_value, entity_id, entity_type)
  idx_fact_values_project_time: (project_agg_id, time_id) INCLUDE (value, metric_id)
  idx_fact_values_base: (metric_id, project_agg_id, time_id) WHERE slice_rule_id IS NULL
  idx_fact_values_entity: (entity_type, entity_id) WHERE entity_id IS NOT NULL

Create view metrics.v_facts:
  SELECT
    fv.id, fv.value, fv.entity_type, fv.entity_id,
    fv.event_start_at, fv.event_end_at,
    fv.slice_value, fv.commitment_rule_id,
    fv.created_at, fv.updated_at,
    c.calc_code, c.unit_code, c.uses_commitment_points,
    d.metric_code,
    g.grain_code,
    dp.project_key,
    dt.full_date, dt.week_num, dt.month_num, dt.quarter, dt.year,
    sr.rule_name AS slice_rule_name
  FROM metrics.fact_values fv
  JOIN metrics.calculations c ON fv.metric_id = c.id
  JOIN metrics.definitions d ON c.definition_id = d.id
  JOIN metrics.grains g ON c.grain_id = g.id
  JOIN metrics.dim_projects dp ON fv.project_agg_id = dp.id
  JOIN metrics.dim_dates dt ON fv.time_id = dt.time_id
  LEFT JOIN metrics.slice_rules sr ON fv.slice_rule_id = sr.id
```

Acceptance criteria:
- `fact_values` table created with all 4 indexes
- `v_facts` view returns data without error
- `SELECT COUNT(*) FROM metrics.v_facts` returns 0 (empty, no data yet)
- `EXPLAIN SELECT value FROM metrics.v_facts WHERE metric_id = 'x' AND project_agg_id = 'y'` shows Index Scan on idx_fact_values_main

---

**Task 0.3 — Migration: seed dim_dates (2020-2030), seed definitions, grains, calculations**

File to create: `db/migrations/versions/0020_seed_metric_metadata.py`

Seed `metrics.grains`:
- ('issue', 'One row per Jira issue')
- ('sprint', 'One row per sprint')
- ('week', 'One row per ISO week')
- ('day', 'One row per calendar day')
- ('release', 'One row per Jira release')

Seed `metrics.definitions` (metric groups):
- velocity, lead_time, throughput, cfd, backlog_growth, ttm, aging, flow_efficiency

Seed `metrics.calculations` (atomic calc codes with FK to definitions and grains):
```
velocity group (grain=sprint, unit_code='story_points' or 'issues'):
  velocity_planned_sp      (unit_code='story_points', grain=sprint, uses_commitment_points=false)
  velocity_completed_sp    (unit_code='story_points', grain=sprint, uses_commitment_points=false)
  velocity_planned_count   (unit_code='issues',       grain=sprint, uses_commitment_points=false)
  velocity_completed_count (unit_code='issues',       grain=sprint, uses_commitment_points=false)

lead_time group (grain=issue):
  lead_time_days           (unit_code='days', grain=issue, uses_commitment_points=true)

throughput group (grain=week):
  throughput_count         (unit_code='issues', grain=week, uses_commitment_points=false)

cfd group (grain=day):
  cfd_count                (unit_code='issues', grain=day, uses_commitment_points=false)

backlog_growth group (grain=day):
  backlog_size             (unit_code='issues', grain=day)
  backlog_created          (unit_code='issues', grain=day)
  backlog_resolved         (unit_code='issues', grain=day)
  backlog_net_growth       (unit_code='issues', grain=day)

ttm group (grain=issue):
  ttm_days                 (unit_code='days', grain=issue, uses_commitment_points=true)

aging group (grain=issue):
  aging_days               (unit_code='days', grain=issue, uses_commitment_points=true)

flow_efficiency group (grain=issue):
  flow_active_days         (unit_code='days',    grain=issue, uses_commitment_points=true)
  flow_wait_days           (unit_code='days',    grain=issue, uses_commitment_points=true)
  flow_efficiency_pct      (unit_code='percent', grain=issue, uses_commitment_points=true)
```

Seed `metrics.dim_dates` for 2020-01-01 to 2030-12-31:
- Generate date range in Python within migration
- Calculate week_num (ISO), month_num, quarter, year for each date
- Format time_id as YYYYMMDD integer
- Bulk insert via executemany or COPY

Seed `metrics.units` (global defaults, project_id=NULL):
- (NULL, 'story_points', 'SP', NULL, NULL)  -- source_field resolved at runtime per project
- (NULL, 'issues', 'items', NULL, NULL)
- (NULL, 'days', 'd', NULL, NULL)
- (NULL, 'hours', 'h', NULL, NULL)
- (NULL, 'percent', '%', NULL, NULL)

Acceptance criteria:
- `SELECT COUNT(*) FROM metrics.grains` = 5
- `SELECT COUNT(*) FROM metrics.definitions` = 8
- `SELECT COUNT(*) FROM metrics.calculations` = 18
- `SELECT COUNT(*) FROM metrics.dim_dates` >= 3652 (2020-2030)
- `SELECT * FROM metrics.calculations WHERE calc_code = 'lead_time_days'` returns 1 row with uses_commitment_points=true

---

### Phase 1: Infrastructure Layer

**Task 1.1 — Update `pipelines/utils/polars_db.py`**

Add new function `write_fact_values()` alongside existing `write_table()`:

```python
def write_fact_values(
    df: pl.DataFrame,
    engine: Engine,
    metric_ids: list[str],
    project_agg_ids: list[str],
    time_id_start: int,
    time_id_end: int,
) -> int:
    """
    Idempotent write of fact_values rows.

    Algorithm:
    1. DELETE rows WHERE metric_id IN (:metric_ids)
                      AND project_agg_id IN (:project_agg_ids)
                      AND time_id BETWEEN :start AND :end
    2. INSERT new rows via ADBC (COPY protocol)

    Returns: number of rows inserted
    """
```

Use `adbc_driver_postgresql` for INSERT (COPY protocol).
Fall back to Pandas `to_sql(method="multi", chunksize=5000)` if ADBC unavailable (graceful degradation).

Keep existing `write_table()` unchanged (still used for old fact_* tables during transition period).

Also improve `read_table()`: replace Pandas bridge with `pl.read_database_uri()` using direct Postgres URI for better performance.

Acceptance criteria:
- `write_fact_values()` function exists and is importable
- Unit test: write 100 rows, verify DELETE+INSERT idempotency (write same rows twice, count = 100 not 200)
- Unit test: verify ADBC path executes without error against real DB
- Old `write_table()` still works (no regression)

---

**Task 1.2 — New `pipelines/utils/metric_registry.py`**

Create module for resolving metadata from new schema:

```python
def get_calculation_id(engine: Engine, calc_code: str) -> str:
    """Return UUID of calculations row by calc_code. Raise if not found."""

def get_definition_id(engine: Engine, metric_code: str) -> str:
    """Return UUID of definitions row by metric_code."""

def get_project_agg_id(engine: Engine, project_id: str) -> str:
    """Return dim_projects.id for given clean_jira project_id. Create if not exists."""

def get_or_create_dim_project(engine: Engine, project_id: str, project_key: str) -> str:
    """Upsert dim_projects row, return id."""

def resolve_commitment_rule(engine: Engine, project_id: str, board_id: str, calc_code: str) -> str | None:
    """
    Return commitment_rules.id for given project/board/calc_code.
    Priority: project+board > project only > global (project_id=NULL).
    Returns None if no rule found.
    """

def resolve_unit_field(engine: Engine, project_id: str, unit_code: str) -> dict | None:
    """
    Return {'source_field_id': uuid, 'source_entity': str} for given project/unit_code.
    Falls back to global (project_id=NULL) rule.
    Returns None if no config found.
    """
```

Cache results in memory within asset execution (simple dict, not Redis).

Acceptance criteria:
- `get_calculation_id(engine, 'lead_time_days')` returns correct UUID from seeded data
- `get_project_agg_id()` creates dim_projects row on first call, returns same ID on second call (idempotent)
- `resolve_commitment_rule()` with no rules in DB returns None without exception
- All functions tested with integration tests against real DB

---

**Task 1.3 — Update `pipelines/calculations/slicing_utils.py`**

Changes required:
1. Update `get_slice_rules()` query: `FROM metrics.metric_slice_rules` → `FROM metrics.slice_rules`
2. Rename query column: `group_by_column` → `group_by_source_column`
3. Remove `filter_condition` parsing entirely (column removed from schema)
4. Update `target_metric_table` filter → `target_definition_id` (FK-based filter)
5. Update return columns: remove `filter_condition`, `slice_table_name`; add `target_definition_id`

Signature change for `get_slice_rules()`:
```python
def get_slice_rules(
    engine: Engine,
    project_id: str | None = None,
    target_definition_id: str | None = None,  # NEW: replaces target_metric_table
) -> pl.DataFrame:
```

The `apply_slicing()` function logic remains the same but remove the `filter_condition` branch entirely.

Acceptance criteria:
- `get_slice_rules(engine)` reads from `metrics.slice_rules` without error
- `apply_slicing()` handles empty rules_df gracefully
- Existing unit tests for slicing logic still pass (update SQL table name in test fixtures)

---

**Task 1.4 — New `pipelines/calculations/commitment_resolver.py`**

Replace hardcoded string matching in `lead_time.py::identify_commitment_points()`.

```python
def resolve_commitment_columns(
    engine: Engine,
    project_id: str,
    board_id: str,
    calc_code: str,  # 'lead_time_days', 'cycle_time_days', etc.
) -> dict | None:
    """
    Query commitment_rules for project/board/calc_code.
    Return {'start_column_id': uuid, 'end_column_id': uuid,
            'start_column_name': str, 'end_column_name': str,
            'commitment_rule_id': uuid}
    Priority: project+board > project_only > global.
    Falls back to column-name heuristic if no rule exists (backward compat).
    """

def identify_commitment_points_from_rule(
    rule: dict,
    board_columns_df: pl.DataFrame,
) -> dict:
    """
    Given a resolved commitment rule, return status_ids and positions.
    Replaces old identify_commitment_points() string-matching logic.
    """

def identify_commitment_points_heuristic(
    board_columns_df: pl.DataFrame,
) -> dict:
    """
    Fallback: use string matching ('in progress', 'done').
    Kept for backward compat when no commitment_rules exist.
    This is the CURRENT behavior extracted into a function.
    """
```

Acceptance criteria:
- `resolve_commitment_columns()` returns correct data when `commitment_rules` has a matching row
- Falls back to heuristic when no rule found
- Lead time calculation with commitment resolver produces same results as current heuristic for standard boards
- Integration test: with rule for project X board Y, uses rule columns; without rule, uses heuristic

---

### Phase 2: Metric Assets — Write to fact_values

**Task 2.1 — Rewrite `pipelines/assets/metrics/velocity.py`**

Current behavior: writes to `metrics.fact_velocity` + `metrics.fact_velocity_slices`
New behavior: writes to `metrics.fact_values` with 4 calc_codes per sprint

Changes:
1. Import `metric_registry` to resolve metric_ids, project_agg_ids
2. At start: load `metric_id` for each of 4 calc_codes (velocity_planned_sp, velocity_completed_sp, velocity_planned_count, velocity_completed_count)
3. Load/create `project_agg_id` for each project
4. Map sprint end_date → `time_id` (YYYYMMDD format)
5. Build long-format DataFrame:
   ```
   columns: [metric_id, project_agg_id, time_id, value, entity_type, entity_id, slice_rule_id, slice_value]
   entity_type = 'sprint'
   entity_id = sprint UUID as string
   ```
6. For slices: apply `apply_slicing()` with new slice_rules, add metric_id for each calc_code
7. Use `write_fact_values()` with metric_ids in scope, project_agg_ids, time_id range
8. Use `units` table via `resolve_unit_field()` to find story points field (replace hardcoded field lookup)

Keep existing `velocity_logic.calculate_velocity_facts()` calculation function UNCHANGED — only the output format and DB write changes.

Acceptance criteria:
- Asset materializes without error
- `SELECT COUNT(*) FROM metrics.fact_values WHERE metric_id IN (SELECT id FROM metrics.calculations WHERE calc_code LIKE 'velocity_%')` > 0
- Each sprint has exactly 4 base rows (one per calc_code) when no slices configured
- Idempotent: running twice produces same row count
- `SELECT value FROM metrics.v_facts WHERE calc_code = 'velocity_completed_sp' AND project_key = 'PROJ' ORDER BY full_date DESC LIMIT 5` returns correct data

---

**Task 2.2 — Rewrite `pipelines/assets/metrics/lead_time.py`**

Current behavior: writes to `metrics.fact_lead_time` + slices + bins
New behavior: writes to `metrics.fact_values` with `lead_time_days` calc_code, including `event_start_at/end_at`

Changes:
1. Use `commitment_resolver.resolve_commitment_columns()` instead of `identify_commitment_points()`
2. Each issue → 1 row in fact_values:
   ```
   metric_id = calculations.id (calc_code='lead_time_days')
   time_id = completion date as YYYYMMDD
   value = lead_time_days (DOUBLE PRECISION)
   entity_type = 'issue'
   entity_id = issue_key (e.g., 'PROJ-123')
   event_start_at = commitment_start timestamp
   event_end_at = commitment_end timestamp
   commitment_rule_id = resolved rule UUID (or NULL if heuristic used)
   ```
3. For slices: add rows with slice_rule_id + slice_value (same event_start_at/end_at)
4. Remove bin calculation (fact_lead_time_bins) — percentiles computed in BI queries from fact_values

The existing `calculate_lead_time_facts()` calculation function can be reused; only output format changes.

Acceptance criteria:
- `SELECT AVG(value) FROM metrics.v_facts WHERE calc_code = 'lead_time_days' AND slice_rule_id IS NULL` returns plausible number
- `event_start_at` and `event_end_at` are populated for all rows where commitment points found
- `(event_end_at - event_start_at)` in days approximately equals `value`
- Running twice: same row count (idempotent DELETE+INSERT by issue entity_id scope)

---

**Task 2.3 — Rewrite `pipelines/assets/metrics/throughput.py`**

Current: writes to `metrics.fact_throughput`
New: writes `throughput_count` per week per project to `fact_values`

```
metric_id = calc 'throughput_count'
time_id = week_start_date as YYYYMMDD (always Monday)
value = count of issues completed in that week
entity_type = 'week'
entity_id = '2026-03-16' (week start date as string)
```

Acceptance criteria:
- `SELECT SUM(value) FROM metrics.v_facts WHERE calc_code = 'throughput_count' AND slice_rule_id IS NULL` equals total issues resolved
- time_id is always a Monday (week_start)
- Sliced rows: sum of slice values per week equals base value for that week

---

**Task 2.4 — Rewrite `pipelines/assets/metrics/cumulative_flow.py`**

Current: writes to `metrics.fact_cfd`
New: writes `cfd_count` per (day × board_column) to `fact_values` using `entity_type='board_column'`

Key change: NO slice_rule_id for CFD — board column IS the primary dimension.
```
metric_id = calc 'cfd_count'
time_id = snapshot date as YYYYMMDD
value = count of issues in this column on this date
entity_type = 'board_column'
entity_id = board_column UUID as string
slice_rule_id = NULL
```

Acceptance criteria:
- `SELECT SUM(value) FROM metrics.v_facts WHERE calc_code = 'cfd_count' AND time_id = 20260318` equals total active issues on 2026-03-18 (conservation check)
- Each (project_agg_id, time_id) combination has N rows = N board columns (one per column)
- Joining `entity_id::uuid` to `clean_jira.board_columns.id` returns column names and positions correctly
- The CFD query in GENERIC_LONG_METRIC_STORE_VISION.md runs correctly

---

**Task 2.5 — Rewrite `pipelines/assets/metrics/backlog_growth.py`**

Current: writes to `metrics.fact_backlog_growth`
New: writes 4 calc_codes per day per project

```
backlog_size, backlog_created, backlog_resolved, backlog_net_growth
All with entity_type = NULL, entity_id = NULL (aggregate, no drill-down)
time_id = snapshot date YYYYMMDD
```

Acceptance criteria:
- `backlog_net_growth` value equals `backlog_created - backlog_resolved` for same project/day
- `backlog_size` decreases when resolved > created
- 4 rows per (project_agg_id, time_id) combination in base (no slice)

---

**Task 2.6 — Rewrite `pipelines/assets/metrics/time_to_market.py`**

Current: writes to `metrics.fact_time_to_market`
New: writes `ttm_days` per released issue to `fact_values`

```
metric_id = calc 'ttm_days'
time_id = release date YYYYMMDD
value = ttm_days
entity_type = 'issue'
entity_id = issue_key
event_start_at = issue.jira_created_at
event_end_at = release date as TIMESTAMPTZ
commitment_rule_id = NULL (not applicable for TTM)
```

Acceptance criteria:
- `(event_end_at - event_start_at)` in days approximately equals `value`
- Only released issues appear (not issues still in backlog)

---

**Task 2.7 — Rewrite `pipelines/assets/metrics/advanced.py`**

Current: writes `fact_work_item_aging` + `fact_flow_efficiency`
New: writes aging_days, flow_active_days, flow_wait_days, flow_efficiency_pct to `fact_values`

Aging:
```
metric_id = calc 'aging_days'
time_id = today YYYYMMDD
value = age_days (how long in current status)
entity_type = 'issue'
entity_id = issue_key
event_start_at = when issue entered current status
event_end_at = NULL (still active)
```

Flow efficiency (3 rows per closed issue):
```
metric_id = calc 'flow_active_days' / 'flow_wait_days' / 'flow_efficiency_pct'
time_id = completion date YYYYMMDD
entity_type = 'issue'
entity_id = issue_key
commitment_rule_id = resolved rule (same as lead_time)
```

Acceptance criteria:
- `flow_efficiency_pct = (flow_active_days / (flow_active_days + flow_wait_days)) * 100` within 0.01 tolerance
- All active issues have an aging_days row for today
- Closed issues do NOT appear in aging

---

### Phase 3: View, Tests, Asset Checks

**Task 3.1 — Update `db/views/metrics.sql`**

Replace all old `mv_*` view definitions with `metrics.v_facts` view definition.
Keep migration-based view creation (in Task 0.2) as source of truth.
The `metrics.sql` file should reflect the current view definition.

Acceptance criteria:
- `metrics.sql` contains the `CREATE OR REPLACE VIEW metrics.v_facts` statement
- View matches what was created in migration 0019

---

**Task 3.2 — Update tests**

Files to update:
- `tests/unit/test_slicing_utils.py`: update SQL fixture table name (`metric_slice_rules` → `slice_rules`), remove `filter_condition` column
- `tests/unit/test_velocity.py`: update expected output format (long format, 4 rows per sprint)
- `tests/integration/test_metrics_*.py`: update table assertions from `fact_velocity` → `fact_values WHERE calc_code = 'velocity_*'`
- Add new `tests/unit/test_metric_registry.py`: test all functions in `metric_registry.py`
- Add new `tests/unit/test_commitment_resolver.py`: test heuristic + rule-based resolution
- Add new `tests/integration/test_fact_values_idempotency.py`: verify write twice = same count

Acceptance criteria:
- `make test` passes with 0 failures
- Coverage >= 75% on new modules

---

**Task 3.3 — Add Dagster asset checks**

File to update: each metric asset file OR a new `pipelines/assets/metrics/checks.py`

For each metric asset, add `@asset_check`:
```python
@asset_check(asset=calculate_velocity)
def velocity_data_quality_check(database: DatabaseResource) -> AssetCheckResult:
    engine = database.get_engine()
    # Check: rows exist for velocity calc_codes
    # Check: no NULL values in fact_values.value for velocity metrics
    # Check: all time_id values map to valid dates in dim_dates
    # Check: no duplicate (metric_id, project_agg_id, time_id, entity_id) for base rows
```

Acceptance criteria:
- All 7 asset checks pass after successful materialization
- Check fails if `fact_values` has 0 rows for that metric
- Check fails if `value IS NULL` for any velocity row

---

### Phase 4: Admin API (optional, lower priority)

**Task 4.1 — API endpoints for slice_rules management**

Files to update: `app/` (FastAPI backend)

Add endpoints:
- `GET /api/slice-rules` — list all active rules
- `POST /api/slice-rules` — create new rule
- `PUT /api/slice-rules/{id}` — update rule
- `DELETE /api/slice-rules/{id}` — soft delete (enabled=false)

**Task 4.2 — API endpoints for commitment_rules management**

- `GET /api/commitment-rules`
- `POST /api/commitment-rules`
- `PUT /api/commitment-rules/{id}`

**Task 4.3 — API endpoints for units management**

- `GET /api/units` — list all unit configs
- `POST /api/units` — create per-project unit config
- `PUT /api/units/{id}` — update
- Auto-populate `dim_projects` from `clean_jira.projects` on startup

Acceptance criteria (Phase 4):
- All endpoints return 200 with correct schema
- Creating a slice_rule via API and rerunning calculate_velocity uses the new rule
- Unit tests for all new endpoints

---

## Critical Findings from Hardcore Review (Added Post-Analysis)

### Broken API Endpoints (Pre-existing, Fix Required)
All 3 main GET endpoints in `app/api/metrics.py` query **dropped MVs** (removed in migration 0014). They are currently broken regardless of this migration:
- `GET /metrics/lead-time` (line 96) → queries `metrics.mv_lead_time` (dropped)
- `GET /metrics/velocity` (line 234) → queries `metrics.mv_velocity` (dropped)
- `GET /metrics/throughput` (line 376) → queries `metrics.mv_throughput` (dropped)
- `POST /metrics/refresh` (line 502) → calls `metrics.refresh_all_views()` (dropped function)

**Action**: Rewrite all 4 endpoints to query `metrics.v_facts` with appropriate calc_code filters in Task 4.1.

### Missing flow_efficiency Dagster Asset
`fact_flow_efficiency_slices` table exists (migration 0015) but:
- No base `fact_flow_efficiency` table
- No Dagster asset to populate it
- Calculation module (`slicing_utils.py` references it) but no `calculate_flow_efficiency` asset

**Action**: Create new `pipelines/assets/metrics/flow_efficiency.py` asset as part of Task 2.7.

### fact_cfd_slices Must Also Be Dropped
Migration 0016 created `metrics.fact_cfd_slices`. CFD in new design uses `entity_type='board_column'` instead of slices. This table must be dropped in the cleanup migration.

### backlog_growth Extra Metrics Decision
Current `fact_backlog_growth` has more metrics than in vision doc:
- `avg_age_days`, `stale_issues_count`, `stale_percentage`, `oldest_issue_days` — NOT in vision doc
**Decision**: Add 4 more calc_codes to `metrics.calculations` seed:
- `backlog_avg_age_days` (unit_code='days', grain=day)
- `backlog_stale_count` (unit_code='issues', grain=day)
- `backlog_oldest_days` (unit_code='days', grain=day)
- `backlog_stale_pct` (unit_code='percent', grain=day)

### Velocity Story Points: Hardcoded Field Lookup (velocity.py:119)
The story points field is currently discovered by scanning `clean_jira.field_keys` for `external_key IN ('customfield_10036','customfield_10016','story_points')`. This must be replaced by `units` table lookup in Task 2.1.

### Concurrent Writes: Advisory Lock Pattern
If two metric assets run concurrently both targeting `fact_values`, the DELETE+INSERT pattern can conflict. Mitigation:
- Each `write_fact_values()` call should use `pg_advisory_xact_lock(hashtext(metric_id::text))` before DELETE
- This serializes concurrent writes for the same metric without blocking different metrics

Add to `write_fact_values()` in Task 1.1.

### Partial Unique Constraint on fact_values
Without a unique constraint, a bug in idempotency logic could create duplicates. Add to Task 0.2:
```sql
CREATE UNIQUE INDEX idx_fact_values_unique
  ON metrics.fact_values (metric_id, project_agg_id, time_id,
                           COALESCE(entity_id, ''),
                           COALESCE(slice_rule_id::text, ''),
                           COALESCE(slice_value, ''));
```

### Seed commitment_rules from Existing Data
Migration 0020 should also auto-seed `commitment_rules` by querying existing boards and finding columns matching current heuristics ("In Progress", "Done" patterns). This ensures backward compatibility on first deploy.

### metric_slice_rules → slice_rules Data Migration
The existing `metric_slice_rules` table has data that must be migrated to `slice_rules`. Migration 0018 must:
1. Create `slice_rules` with new schema
2. Copy data from `metric_slice_rules` (mapping `group_by_column` → `group_by_source_column`, `target_metric_table` → resolve to `target_definition_id`)
3. Drop `metric_slice_rules` (after FK updates in e17a9cb848b6 migration)

---

## Execution Order (Strict Dependencies)

```
0.1 → 0.2 → 0.3  (schema must exist before seeding)
    ↓
1.1, 1.2, 1.3, 1.4  (infrastructure, parallel)
    ↓
2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7  (assets, can be parallel after phase 1)
    ↓
3.1, 3.2, 3.3  (tests and view update after assets work)
    ↓
4.1, 4.2, 4.3  (API, lowest priority, can be done last)
```

---

## Plan Review: Reliability, Scalability, Engineering Quality

### Reliability ✅
- Idempotent writes (DELETE+INSERT) prevent duplicate data on reruns
- Transactional writes (engine.begin()) prevent partial writes
- Backward compatibility: old `fact_*` tables kept during transition (drop only after validation)
- Fallback heuristic in commitment_resolver preserves current behavior for boards without rules
- Asset checks catch data quality issues before Metabase sees bad data

### Scalability ✅
- fact_values covering indexes enable O(log N) BI queries instead of full scans
- ADBC/COPY protocol for writes: 10-50x faster than current Pandas method="multi"
- Partitioning strategy documented (yearly RANGE), can be added without full rewrite
- LazyFrame + collect() pattern prevents OOM on large datasets
- No N+1 in slice resolution (rules loaded once per asset run)

### Engineering Quality ✅
- Single source of truth: metric definitions in DB, not hardcoded in Python
- Separation of concerns: calculation logic unchanged, only output format changes
- Registry pattern (metric_registry.py) centralizes all metadata resolution
- Commitment resolver makes boundary logic explicit and configurable
- Regular view (not materialized) = always fresh, no maintenance
- Test coverage requirement: 75% minimum on new modules

### Risks & Mitigations
| Risk | Mitigation |
|------|-----------|
| ADBC not available in some envs | Graceful fallback to Pandas in write_fact_values() |
| commitment_rules table empty on deploy | Heuristic fallback in commitment_resolver |
| dim_dates missing for future dates | Seeded through 2030, extend migration if needed |
| Breaking Metabase dashboards | Old mv_* views kept during transition period |
| fact_values grows large | Indexes + partition strategy; yearly cleanup |

---

## Files to Create/Modify Summary

### New files:
- `db/migrations/versions/0018_add_generic_metric_store_foundation.py`
- `db/migrations/versions/0019_add_fact_values_and_view.py`
- `db/migrations/versions/0020_seed_metric_metadata.py`
- `pipelines/utils/metric_registry.py`
- `pipelines/calculations/commitment_resolver.py`
- `tests/unit/test_metric_registry.py`
- `tests/unit/test_commitment_resolver.py`
- `tests/integration/test_fact_values_idempotency.py`

### Modified files:
- `pipelines/utils/polars_db.py` — add write_fact_values(), improve read_table()
- `pipelines/calculations/slicing_utils.py` — update table name, column names, remove filter_condition
- `pipelines/assets/metrics/velocity.py` — write to fact_values
- `pipelines/assets/metrics/lead_time.py` — use commitment_resolver, write to fact_values
- `pipelines/assets/metrics/throughput.py` — write to fact_values
- `pipelines/assets/metrics/cumulative_flow.py` — entity_type=board_column, write to fact_values
- `pipelines/assets/metrics/backlog_growth.py` — write to fact_values
- `pipelines/assets/metrics/time_to_market.py` — write to fact_values
- `pipelines/assets/metrics/advanced.py` — write to fact_values
- `db/views/metrics.sql` — update to v_facts view
- `tests/unit/test_slicing_utils.py` — update for new schema
- Various test files — update assertions

### Preserved (no changes):
- All `pipelines/calculations/*.py` logic functions (velocity_logic, lead_time_logic, etc.)
- `clean_jira` schema (unchanged)
- `raw_jira` schema (unchanged)
- `platform` schema (unchanged)
- `pipelines/assets/jira/` (unchanged)
- Existing `fact_*` tables (kept until transition validated, then dropped separately)
