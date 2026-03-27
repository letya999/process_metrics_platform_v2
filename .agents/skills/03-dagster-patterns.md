---
name: dagster-patterns
description: Dagster asset structure, groups, resource injection, and scheduling rules. Patterns emerged from production issues, not from docs.
triggers:
  - "dagster"
  - "asset"
  - "@asset"
  - "asset_check"
  - "schedule"
  - "sensor"
  - "DatabaseResource"
context:
  - agent.md
  - .agents/skills/02-database-patterns.md
---

# Skill: Dagster Asset Patterns

Dagster-specific rules for this project. The patterns here are not obvious from documentation — they emerged from production issues.

---

## Asset Anatomy

Every metric asset follows this structure:

```python
@asset(
    group_name="metrics",                          # required: "jira_raw" | "jira_clean" | "metrics"
    deps=["clean_jira_issues", "clean_jira_sprints"],  # ALL upstream assets, explicit
    compute_kind="python",                          # "python" for Polars, "sql" only for pure SQL
    description="One-line description of what this measures",
)
def calculate_my_metric(database: DatabaseResource) -> None:
    # resource injection — Dagster resolves this automatically
    engine = database.get_engine()
    ...
```

Return type is `None` — assets in this project produce side-effects (DB writes), not return values.

---

## compute_kind Values

| Value | When to use |
|---|---|
| `"python"` | Asset runs Python logic (Polars calculations, conditional branches, loops) |
| `"sql"` | Asset is purely a SQL operation with no Python control flow — rare |

**Rule:** If your asset has any `if`, `for`, `while`, Polars operation, or Python variable assignment — use `"python"`. The only valid `"sql"` case is an asset that literally just runs `conn.execute(text("..."))` with no branching.

Misleading `compute_kind="sql"` on Python-heavy assets causes confusion in Dagster UI and misleads agents into thinking the asset can be replaced with a SQL file.

---

## Resource Injection

Only `DatabaseResource` exists as a resource:

```python
from pipelines.resources.database import DatabaseResource

def my_asset(database: DatabaseResource) -> None:
    engine = database.get_engine()
```

`DatabaseResource` is a `ConfigurableResource` backed by sync SQLAlchemy. It caches engines by connection string via `lru_cache`. Never instantiate it manually in tests — use the fixture.

---

## Asset Dependencies

Always declare all upstream assets in `deps=[]`. Dagster uses this to build the lineage graph and to determine execution order.

```python
# CORRECT: explicit deps
@asset(
    deps=["clean_jira_sprint_issues", "clean_jira_sprints", "clean_jira_issues"],
    ...
)

# WRONG: implicit (Dagster won't know the dependency)
@asset(...)
def my_asset(database: DatabaseResource) -> None:
    df = read_table(engine, "clean_jira.sprint_issues")  # reads sprint_issues but no dep declared
```

If an upstream asset hasn't materialized yet, Dagster will not block your asset — it will just run with empty/stale data. Explicit deps prevents this by enforcing materialization order.

---

## Asset Checks

Every metric asset MUST have a companion `@asset_check`. Place it in the same file.

```python
@asset_check(asset=calculate_my_metric_asset)   # reference the asset function by name
def my_metric_data_check(database: DatabaseResource) -> AssetCheckResult:
    engine = database.get_engine()
    calc_id = get_calculation_id(engine, "my_calc_code")  # get_calculation_id, not get_calc_id

    with engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM metrics.fact_values WHERE metric_id = :mid"),
            {"mid": calc_id},
        ).scalar()

    return AssetCheckResult(
        passed=(count or 0) > 0,
        severity=AssetCheckSeverity.WARN,  # WARN not ERROR — don't block pipeline
        description=f"my_metric: {count} rows",
    )
```

**Severity rules:**
- `WARN` — use for all informational metric checks; failure is recoverable on the next run
- `ERROR` — use only when the data must be correct before downstream assets proceed (e.g., dimension tables that metrics depend on for FK resolution)

Default: always start with `WARN`. Escalate to `ERROR` only if a downstream asset will produce wrong data when this check fails.

---

## Logging

Inside assets, always use Dagster context logger OR standard `logging`:

```python
import logging
logger = logging.getLogger(__name__)

# In asset body:
logger.info("Processing %d issues for project %s", len(df), project_key)
logger.warning("No commitment rule found for project %s, using defaults", project_key)
```

Never use `print()` in assets — output is not captured by Dagster's run logs.

---

## Schedules and Jobs

All schedules are defined in `pipelines/jobs/schedules.py`. The pattern:

```python
from dagster import DefaultScheduleStatus, ScheduleDefinition, define_asset_job

# Job (no schedule — manual trigger only)
recalculate_my_metric_job = define_asset_job(
    name="recalculate_my_metric_job",
    selection=[calculate_my_metric],
)

# Scheduled job (default STOPPED — operator must enable in UI)
my_metric_schedule = ScheduleDefinition(
    job=recalculate_my_metric_job,
    cron_schedule="0 * * * *",
    default_status=DefaultScheduleStatus.STOPPED,  # ALWAYS STOPPED — never RUNNING
)
```

**All schedules default to STOPPED.** This is intentional. Enabling a schedule is an explicit operator decision. Never set `DefaultScheduleStatus.RUNNING`.

---

## Definitions Entry Point

`pipelines/definitions.py` is the single Dagster entry point. After adding a new asset:

```python
# 1. Import the asset and check
from pipelines.assets.metrics.my_metric import calculate_my_metric, my_metric_data_check

# 2. Add to asset_checks list
asset_checks = [
    ...,
    my_metric_data_check,
]

# 3. Add job to jobs list
from pipelines.jobs.schedules import recalculate_my_metric_job
jobs = [
    ...,
    recalculate_my_metric_job,
]

# 4. The asset itself is auto-discovered via load_assets_from_modules()
# — no need to add it explicitly to assets list if module is already included
```

---

## Sensor (project partitions)

`pipelines/partitions.py` contains the `sync_project_partitions_sensor`. This sensor:
- Watches `platform.projects` for changes
- Updates Dagster partition definitions when projects are added/removed

It's wrapped in `try/except ImportError` to prevent hard failures during Dagster cold start when DB is not yet ready. Do not remove this guard.

---

## Early-Exit Pattern

When input data is empty, return early and log:
```python
if issues_df.is_empty():
    logger.info("No data for %s — skipping", CALC_CODE)
    return  # Do NOT raise an exception — empty input is valid
```

Raising an exception on empty input fails the asset run and triggers alerts. An empty result is normal during initial setup.

---

## Error Handling in Assets

```python
try:
    result = calculate_complex_thing(df)
except ValueError as e:
    logger.error("Calculation failed for project %s: %s", project_key, e)
    raise  # Re-raise so Dagster marks the asset as failed
```

Never silently swallow exceptions. Always re-raise or let them propagate so Dagster can mark the run as failed and retry.

---

## Testing Assets

Unit tests should NOT instantiate real `DatabaseResource`. Use a mock:

```python
from unittest.mock import MagicMock
import polars as pl

def test_calculate_my_metric():
    # Test the calculation function directly, not the asset
    issues_df = pl.DataFrame({...})
    result = calculate_my_metric(issues_df, ...)
    assert result.shape[0] > 0
```

For asset integration tests, use `build_asset_context()` from `dagster` (public API in Dagster >=1.5):
```python
from dagster import build_asset_context
ctx = build_asset_context()
```
