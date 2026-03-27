---
name: metrics-layer
description: Metrics (Gold) layer - Generic Long Metric Store. All metrics share fact_values. Registry functions, v_facts view, and query patterns.
triggers:
  - "metrics layer"
  - "metrics schema"
  - "fact_values"
  - "v_facts"
  - "metric registry"
  - "get_calculation_id"
  - "get_definition_id"
  - "gold layer"
context:
  - agent.md
  - .agents/skills/11-anti-patterns.md
---

# Skill: Metrics Layer (Generic Long Metric Store)

The metrics schema is the Gold tier. All 20+ metrics share a single fact table.
Understanding this schema is required before modifying any metric.

---

## Core Principle

Every metric value is stored as a single row in `metrics.fact_values`.
There are no separate tables per metric. This is the "Generic Long Metric Store" pattern.

Benefit: Adding a new metric requires no schema change, only a seed migration.
Cost: Complex queries need JOIN through registry tables.

---

## Registry Tables (What, Grain, Unit)

### `metrics.definitions` — metric groups
```sql
id UUID PK, metric_code TEXT UNIQUE
-- Examples: 'velocity', 'lead_time', 'throughput', 'cfd', 'aging'
```

### `metrics.calculations` — specific calculation variants
```sql
id UUID PK,
definition_id UUID FK→definitions,
calc_code TEXT UNIQUE,         -- e.g. 'velocity_planned_sp', 'velocity_completed_count'
grain_id UUID FK→grains,
unit_code TEXT,                -- 'story_points' | 'issue_count' | 'days' | 'percent'
uses_commitment_points BOOLEAN
```

### `metrics.grains` — time/entity granularity
```sql
id UUID PK, grain_code TEXT UNIQUE
-- Values: 'issue', 'sprint', 'day', 'week', 'release'
```

### `metrics.dim_projects` — project dimension
```sql
id UUID PK,
project_id UUID FK→clean_jira.projects.id,
project_key TEXT               -- e.g. 'MYPROJ'
```

### `metrics.dim_dates` — date dimension
```sql
time_id INT PK,                -- format YYYYMMDD, e.g. 20260115
date DATE,
week INT, month INT, quarter INT, year INT
```

---

## `metrics.fact_values` — The Core Table

```sql
id                UUID PK
metric_id         UUID FK→calculations.id   -- WHAT was measured
project_agg_id    UUID FK→dim_projects.id   -- WHICH project
time_id           INT  FK→dim_dates.time_id -- WHEN (YYYYMMDD)
value             FLOAT8                    -- numeric measurement
entity_type       TEXT                      -- 'issue', 'sprint', 'day', 'week', 'release'
entity_id         TEXT                      -- issue key, sprint UUID, date string
event_start_at    TIMESTAMPTZ               -- for lead/cycle time: start timestamp
event_end_at      TIMESTAMPTZ               -- completion timestamp
slice_rule_id     UUID FK→slice_rules.id    -- NULL = unsliced aggregate
slice_value       TEXT                      -- e.g. 'Bug', 'High', 'Team A'
commitment_rule_id UUID FK→commitment_rules.id  -- NULL if not flow-based
settings_id       UUID FK→calculation_settings.id
context_json      JSONB                     -- extra context (assignee, components, etc.)
```

One fact row = one measurement for one entity in one project at one time.

---

## `metrics.v_facts` View

Denormalized view joining all registries. Human-readable output:

```sql
calc_code, metric_code, grain_code, unit_code,
project_key,
date,           -- DATE from dim_dates
time_id,        -- INT for Metabase filtering
value,
entity_type, entity_id,
event_start_at, event_end_at,
slice_value, context_json
```

Use this for: Metabase, debug queries, aggregate statistics.
Do NOT write to this view — write to `fact_values` only.

---

## Configuration Tables

### `metrics.units` — story points field binding
```sql
id UUID PK,
project_id UUID NULLABLE,       -- NULL = global default
unit_code TEXT,                  -- 'story_points'
source_field TEXT                -- Jira field ID, e.g. 'customfield_10036'
```

Priority: project-specific entry first, then global (project_id IS NULL).

To configure story points for a project:
```sql
INSERT INTO metrics.units (id, project_id, unit_code, source_field)
VALUES (gen_random_uuid(), 'project-uuid', 'story_points', 'customfield_10036')
ON CONFLICT DO NOTHING;
```

Or via Admin API: `PUT /api/v1/admin/units`.

### `metrics.slice_rules` — how to segment metrics
```sql
id UUID PK,
name TEXT,
target_definition_id UUID FK→definitions,   -- which metric group
source_table TEXT,                          -- e.g. 'clean_jira.issues'
group_by_source_column TEXT,               -- e.g. 'type_name', 'priority_name'
filter_value TEXT NULLABLE                 -- optional: only this value
```

Example: slice velocity by issue type →
`source_table='clean_jira.issues'`, `group_by_source_column='type_name'`

### `metrics.commitment_rules` — board entry/exit columns
```sql
id UUID PK,
project_id UUID,
board_id UUID,
start_column_id UUID FK→clean_jira.board_columns,
end_column_id UUID FK→clean_jira.board_columns
```

Determines which board columns define "work started" and "work done" for flow metrics.

### `metrics.calculation_settings` — per-metric config
```sql
id UUID PK,
calc_code TEXT,
project_id UUID NULLABLE,
setting_key TEXT,
setting_value JSONB
```

Priority: project-specific (project_id = X) overrides global (project_id IS NULL).

---

## UUID Lookups — Use Registry, Not Raw SQL

Never hardcode UUIDs. Always resolve via `metric_registry.py`:

```python
from pipelines.utils.metric_registry import (
    get_calculation_id,       # calc_code → UUID str in metrics.calculations
    get_definition_id,        # metric_code → UUID str in metrics.definitions
    get_project_agg_id,       # clean_jira project_id → UUID str in metrics.dim_projects
    get_project_agg_ids_batch,# batch version — preferred in loops
    resolve_unit_field,       # project_id + unit_code → dict or None
    clear_cache,              # clear all cached lookups (useful in tests)
)

# Functions that do NOT exist (do not use):
# get_calc_id, get_grain_id, get_calc_settings, clear_all_caches

calc_id = get_calculation_id(engine, "velocity_planned_sp")
project_agg_id = get_project_agg_id(engine, str(project_uuid))
# For multiple projects, use batch:
agg_map = get_project_agg_ids_batch(engine, [str(p) for p in project_ids])
```

`resolve_unit_field()` returns `dict {"source_field_id": str, "source_entity": str}` or `None` — NOT a string field key.

All lookups are cached with 5-minute TTL and protected by `threading.Lock`.

---

## Idempotent Write Contract

`write_fact_values(df, engine, metric_ids, project_agg_ids, time_id_start, time_id_end)` deletes then re-inserts:

```
DELETE WHERE metric_id = ANY(metric_ids)
         AND project_agg_id = ANY(project_agg_ids)
         AND time_id BETWEEN time_id_start AND time_id_end
```

Note argument order: `df` first, `engine` second. Caller must compute time range explicitly.

This means:
- Re-running a metric asset is safe
- The time range of the new data determines what gets replaced
- Data outside the time range of the new batch is NOT deleted

Implication: if a historical sprint is updated, only re-materialize with a full-history run (no time range restriction).

---

## Adding dim_dates Entries

`dim_dates` must have rows for all dates you write. The table is pre-seeded in migration `0003` for years 2020–2030. If you write data outside this range, you will get a FK violation.

To extend the range:
```sql
INSERT INTO metrics.dim_dates (time_id, date, week, month, quarter, year)
SELECT
    TO_CHAR(d, 'YYYYMMDD')::INT,
    d,
    EXTRACT(WEEK FROM d)::INT,
    EXTRACT(MONTH FROM d)::INT,
    EXTRACT(QUARTER FROM d)::INT,
    EXTRACT(YEAR FROM d)::INT
FROM generate_series('2031-01-01'::date, '2035-12-31'::date, '1 day'::interval) AS d
ON CONFLICT DO NOTHING;
```

---

## Metabase Integration

Metabase is configured to query `metrics.v_facts` directly. Dashboard SQL examples:

```sql
-- Velocity trend
SELECT date, value, slice_value
FROM metrics.v_facts
WHERE calc_code = 'velocity_completed_sp'
  AND project_key = 'MYPROJ'
  AND date >= CURRENT_DATE - INTERVAL '90 days'
ORDER BY date;
```

When adding a new metric, test the Metabase query manually before building dashboards.
