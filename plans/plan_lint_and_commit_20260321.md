# Plan: Lint Check and Commit

## Date
2026-03-21

## Objective
Run ruff linter on all changed files, auto-fix any fixable issues, then create a git commit with all staged changes from the metrics expansion and calculation unification work.

## Context
Branch: `metrics-expansion-and-calculation-unification`

All 256 unit + integration tests are passing. The following changes need to be linted and committed:

### Modified files
- `app/api/metrics.py`
- `db/views/metrics.sql`
- `tests/integration/test_dagster_assets.py`
- `tests/unit/test_aging.py`
- `tests/unit/test_lead_time_logic.py`
- `tests/unit/test_metric_assets_generic_store.py`
- `tests/unit/test_time_to_market.py`

### New files
- `db/migrations/versions/0023_add_calculation_settings.py`
- `db/migrations/versions/0024_add_fact_values_columns.py`
- `db/migrations/versions/0025_drop_legacy_fact_tables.py`
- `METRICS_AS_IS_TO_BE.md`
- `METRICS_VISION.md`
- `plans/plan_lint_and_commit_20260321.md`

### Deleted files
- `sprints_velocity.md`
- `velocity_anomaly_investigation.md`

### Previously committed (already in branch via prior commits) but also modified by this session:
Check git diff to see which of the pipeline files were already committed in earlier sessions vs need staging now:
- `pipelines/utils/polars_db.py`
- `pipelines/utils/metric_registry.py`
- `pipelines/calculations/commitment_resolver.py`
- `pipelines/assets/metrics/velocity.py`
- `pipelines/assets/metrics/lead_time.py`
- `pipelines/calculations/backlog_growth.py`
- `pipelines/calculations/throughput.py`
- `pipelines/calculations/time_to_market.py`
- `pipelines/calculations/aging.py`
- `pipelines/assets/metrics/refresh.py`

## Steps

### Step 1: Run ruff linter with auto-fix
```bash
cd C:\Users\User\a_projects\process_metrics_platform_v2
uv run ruff check . --fix
uv run ruff format .
```

### Step 2: Run tests again to confirm lint fixes didn't break anything
```bash
uv run pytest tests/unit/ tests/integration/ -q
```

### Step 3: Stage all relevant files
```bash
git add app/api/metrics.py
git add db/views/metrics.sql
git add db/migrations/versions/0023_add_calculation_settings.py
git add db/migrations/versions/0024_add_fact_values_columns.py
git add db/migrations/versions/0025_drop_legacy_fact_tables.py
git add tests/integration/test_dagster_assets.py
git add tests/unit/test_aging.py
git add tests/unit/test_lead_time_logic.py
git add tests/unit/test_metric_assets_generic_store.py
git add tests/unit/test_time_to_market.py
git add METRICS_AS_IS_TO_BE.md
git add METRICS_VISION.md
git rm sprints_velocity.md
git rm velocity_anomaly_investigation.md
# Also add any pipeline files showing as modified
git add pipelines/
```

### Step 4: Create commit
Commit message (no AI attribution, no co-author):
```
feat: metrics expansion and calculation unification

- Add calculation_settings table (0023) for per-project metric config
- Add settings_id UUID + context_json JSONB to fact_values (0024)
- Drop legacy fact tables and slices tables (0025)
- Rewrite API endpoints to query metrics.v_facts generic store
- Atomic DELETE+INSERT in write_fact_values via staging temp table
- TTL-based cache (5min) in metric_registry to avoid stale data
- Extract shared helpers to commitment_resolver (DRY fix)
- Replace cartesian cross join with event-based approach in backlog_growth
- Fix test contracts for aging, lead_time, time_to_market, metric_assets
```

## Important Rules
- NO Co-Authored-By lines
- NO AI attribution
- English only
- Only commit files listed above (do not accidentally commit logs.txt or .python-version)
