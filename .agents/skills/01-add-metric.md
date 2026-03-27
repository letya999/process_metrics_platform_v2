---
name: add-metric
description: Step-by-step guide for adding a metric end-to-end. All 6 steps are mandatory. Use when asked to add, implement, or create a new metric.
triggers:
  - "add a metric"
  - "new metric"
  - "implement metric"
  - "create metric"
context:
  - agent.md
  - .agents/skills/02-database-patterns.md
  - .agents/skills/07-metrics-layer.md
  - .agents/skills/09-polars-patterns.md
  - .agents/skills/04-testing-patterns.md
  - .agents/skills/11-anti-patterns.md
---

# Skill: Adding a New Metric

Complete guide for adding a metric end-to-end. All 6 steps are mandatory — partial implementation leaves the system in an inconsistent state.

---

## Conceptual Model

A metric is a named time-series value computed from Jira events and stored in `metrics.fact_values`.

```
Event source (clean_jira.*) → Polars calculation → long-format DataFrame → fact_values
```

The system stores ALL metric variants in one table. Every row is identified by:
- **what** was measured: `metric_id` → `metrics.calculations.calc_code`
- **which project**: `project_agg_id` → `metrics.dim_projects`
- **when**: `time_id` (YYYYMMDD INT) → `metrics.dim_dates`
- **which entity**: `entity_type` + `entity_id` (sprint UUID, issue key, etc.)
- **which slice** (optional): `slice_rule_id` + `slice_value`

---

## Event Sources (where raw data comes from)

| Source table | Used for |
|---|---|
| `clean_jira.issues` | Aging, backlog state, issue attributes |
| `clean_jira.issue_status_changelog` | Lead time, cycle time, CFD, flow efficiency |
| `clean_jira.sprint_issues` + `clean_jira.sprints` | Velocity, sprint health, scope change |
| `clean_jira.board_columns` + `clean_jira.board_column_statuses` | Commitment rule resolution |
| `clean_jira.field_values` | Story points current value |
| `clean_jira.field_value_changelog` | Estimation volatility (SP changes over time) |
| `clean_jira.releases` + `clean_jira.release_issues` | Delivery metrics, TTM |

Load via `read_table(engine, query)` from `pipelines/utils/polars_db.py`.

---

## Grains

The grain defines the unit of measurement per row in `fact_values`:

| grain_code | entity_type | entity_id | time_id | Typical metrics |
|---|---|---|---|---|
| `issue` | `"issue"` | issue key (e.g. `"PROJ-123"`) | completion date YYYYMMDD | lead_time, aging, cycle_time |
| `sprint` | `"sprint"` | sprint UUID as string | sprint end date YYYYMMDD | velocity, sprint_health |
| `day` | `"day"` | date string `"YYYY-MM-DD"` | date as YYYYMMDD | throughput, CFD, input_flow |
| `week` | `"week"` | ISO week string `"YYYY-WNN"` | week start as YYYYMMDD | cancellation_rate, input_flow_weekly |
| `release` | `"release"` | release name string | release date YYYYMMDD | delivery metrics |

The grain_code must exist in `metrics.grains` table.

**Grain selection rule:**
- `issue` — event per completed issue (lead_time, cycle_time, aging)
- `sprint` — one value per sprint iteration (velocity, sprint_health)
- `day` — one value per calendar day (throughput, CFD, input_flow)
- `week` — one value per ISO week (cancellation_rate, weekly summaries)
- `release` — one value per release/version (delivery metrics, TTM)

---

## Units

Units resolve which Jira custom field holds story points for a given project.

```python
from pipelines.utils.metric_registry import resolve_unit_field

# Returns dict {"source_field_id": "<uuid>", "source_entity": "field_values"} or None
unit_info = resolve_unit_field(engine, project_id, "story_points")

if unit_info:
    # source_field_id is a UUID from clean_jira.field_keys.id
    # Use it to filter clean_jira.field_values
    sp_field_uuid = unit_info["source_field_id"]
    sp_values_df = read_table(
        engine,
        "SELECT fv.issue_id, fv.value_numeric FROM clean_jira.field_values fv "
        "WHERE fv.field_key_id = :fk_id",
        {"fk_id": sp_field_uuid},
    )
```

Two unit codes:
- `story_points` — requires field resolution via `metrics.units` (DB) or fallback to `STORY_POINTS_FIELD_CANDIDATES` constants
- `issue_count` — always 1.0 per issue, no field resolution needed

---

## Calculation Settings

Per-metric configuration stored in `metrics.calculation_settings`. There is no helper function — query it directly:

```python
from sqlalchemy import text

def _get_calc_settings(engine, calc_code: str, project_id: str) -> dict:
    """Load settings for a calculation, project-specific overrides global."""
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT setting_key, setting_value
                FROM metrics.calculation_settings
                WHERE calc_code = :calc_code
                  AND (project_id = :pid OR project_id IS NULL)
                ORDER BY project_id NULLS LAST
            """),
            {"calc_code": calc_code, "pid": project_id},
        ).fetchall()
    # Merge: project-specific wins over global
    result = {}
    for key, value in reversed(rows):  # global first, then project-specific overwrites
        result[key] = value
    return result

# Usage:
settings = _get_calc_settings(engine, "my_calc_code", project_id)
active_statuses = settings.get("active_statuses", ["In Progress"])
```

---

## Step-by-Step Implementation

### Step 1: `pipelines/calculations/my_metric.py`

Pure Polars logic. No database calls. Takes DataFrames, returns DataFrame.

```python
import polars as pl


def calculate_my_metric(
    issues_df: pl.DataFrame,
    changelog_df: pl.DataFrame,
    *,
    active_statuses: list[str],
) -> pl.DataFrame:
    """
    Args:
        issues_df: rows from clean_jira.issues for one project
        changelog_df: rows from clean_jira.issue_status_changelog for same project
        active_statuses: status names counting as active work

    Returns:
        DataFrame with columns: issue_key, project_id, value, completed_at
        One row per completed issue.
    """
    if issues_df.is_empty():
        return pl.DataFrame(schema={
            "issue_key": pl.Utf8,
            "project_id": pl.Utf8,
            "value": pl.Float64,
            "completed_at": pl.Datetime("us", "UTC"),
        })
    # ... pure Polars logic
    return result_df
```

Rules:
- No imports from `pipelines.resources`, `pipelines.utils.polars_db`, or `app.*`
- All inputs as Polars DataFrames
- Output must include `project_id` for downstream grouping
- Always return empty DataFrame with correct schema when input is empty

### Step 2: `pipelines/assets/metrics/my_metric.py`

The Dagster asset that orchestrates load → calculate → write.

```python
import logging
from datetime import UTC, datetime

import polars as pl
from dagster import AssetCheckResult, AssetCheckSeverity, asset, asset_check
from sqlalchemy import text

from pipelines.calculations.my_metric import calculate_my_metric
from pipelines.calculations.slicing_utils import apply_slicing, get_slice_rules
from pipelines.resources.database import DatabaseResource
from pipelines.utils.metric_registry import (
    get_calculation_id,
    get_definition_id,
    get_project_agg_ids_batch,
    resolve_unit_field,
)
from pipelines.utils.polars_db import read_table, write_fact_values

logger = logging.getLogger(__name__)

CALC_CODE = "my_metric_days"    # unique identifier, matches metrics.calculations.calc_code
METRIC_CODE = "my_metric"       # matches metrics.definitions.metric_code
GRAIN = "issue"                 # grain_code from metrics.grains


@asset(
    group_name="metrics",
    deps=["clean_jira_issues", "clean_jira_issue_status_changelog"],
    compute_kind="python",
    description="My metric: brief description of what it measures",
)
def calculate_my_metric_asset(database: DatabaseResource) -> None:
    engine = database.get_engine()

    # 1. Resolve metadata UUIDs (cached, never hardcode)
    calc_id = get_calculation_id(engine, CALC_CODE)
    definition_id = get_definition_id(engine, METRIC_CODE)

    # 2. Load source data (full table — clean layer is always consistent)
    issues_df = read_table(engine, "SELECT * FROM clean_jira.issues")
    changelog_df = read_table(engine, "SELECT * FROM clean_jira.issue_status_changelog")

    if issues_df.is_empty():
        logger.info("No issues found, skipping %s", CALC_CODE)
        return

    # 3. Resolve project agg IDs in batch (efficient — one query for all projects)
    # IMPORTANT: convert to str immediately — Polars filters must match the column type
    # (psycopg2 may return UUID objects; always cast to str for consistent filtering)
    project_ids = [str(p) for p in issues_df["project_id"].unique().to_list()]
    project_agg_map = get_project_agg_ids_batch(engine, project_ids)

    # 4. Load slice rules for this metric
    slice_rules_df = get_slice_rules(engine, target_definition_id=definition_id)

    # 5. Calculate unsliced aggregate per project
    all_rows: list[dict] = []

    for project_id_str in project_ids:
        project_agg_id = project_agg_map[project_id_str]
        # Filter using str — matches after the cast above
        project_issues = issues_df.filter(pl.col("project_id").cast(pl.Utf8) == project_id_str)
        project_changelog = changelog_df.filter(pl.col("project_id").cast(pl.Utf8) == project_id_str)

        # Load per-project settings (falls back to global if no project override)
        settings = _get_calc_settings(engine, CALC_CODE, project_id_str)
        active_statuses = settings.get("active_statuses", ["In Progress"])

        # Unsliced calculation
        result_df = calculate_my_metric(
            project_issues, project_changelog, active_statuses=active_statuses
        )

        for row in result_df.iter_rows(named=True):
            all_rows.append({
                "metric_id": calc_id,
                "project_agg_id": project_agg_id,
                "time_id": int(row["completed_at"].strftime("%Y%m%d")),
                "value": float(row["value"]),
                "entity_type": GRAIN,
                "entity_id": str(row["issue_key"]),
                "event_end_at": row["completed_at"],
                "slice_rule_id": None,
                "slice_value": None,
                "commitment_rule_id": None,
                "settings_id": None,
                "context_json": None,
            })

    # 6. Apply slicing (if rules exist)
    if not slice_rules_df.is_empty():
        # apply_slicing takes a calculation_func that accepts a filtered df
        def _calc_for_slicing(subset_df: pl.DataFrame) -> pl.DataFrame:
            # changelog is global — filter to project inside calculation if needed
            # Use same default settings; per-project override not applied here (global fallback)
            return calculate_my_metric(
                subset_df, changelog_df, active_statuses=["In Progress"]
            )

        sliced_df = apply_slicing(
            issues_df,
            slice_rules_df,
            _calc_for_slicing,
            engine,
            source_table="clean_jira.issues",
        )

        for row in sliced_df.iter_rows(named=True):
            row_project_id = str(row.get("project_id", ""))
            project_agg_id = project_agg_map.get(row_project_id)
            if project_agg_id is None:  # explicit None check — never falsy on valid UUID
                continue
            all_rows.append({
                "metric_id": calc_id,
                "project_agg_id": project_agg_id,
                "time_id": int(row["completed_at"].strftime("%Y%m%d")),
                "value": float(row["value"]),
                "entity_type": GRAIN,
                "entity_id": str(row["issue_key"]),
                "event_end_at": row["completed_at"],
                "slice_rule_id": row.get("slice_rule_id"),
                "slice_value": row.get("slice_value"),
                "commitment_rule_id": None,
                "settings_id": None,
                "context_json": None,
            })

    if not all_rows:
        logger.info("No results for %s", CALC_CODE)
        return

    # 7. Write atomically — requires time range and explicit IDs
    fact_df = pl.DataFrame(all_rows)
    time_ids = fact_df["time_id"].to_list()
    project_agg_ids = fact_df["project_agg_id"].unique().to_list()

    rows_written = write_fact_values(
        fact_df,
        engine,
        metric_ids=[calc_id],
        project_agg_ids=project_agg_ids,
        time_id_start=min(time_ids),
        time_id_end=max(time_ids),
    )
    logger.info("Wrote %d rows for %s", rows_written, CALC_CODE)


@asset_check(asset=calculate_my_metric_asset)
def my_metric_data_check(database: DatabaseResource) -> AssetCheckResult:
    engine = database.get_engine()
    calc_id = get_calculation_id(engine, CALC_CODE)

    with engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM metrics.fact_values WHERE metric_id = :mid"),
            {"mid": calc_id},
        ).scalar()

    return AssetCheckResult(
        passed=(count or 0) > 0,
        severity=AssetCheckSeverity.WARN,
        description=f"{CALC_CODE}: {count} rows in fact_values",
    )
```

### Step 3: `pipelines/assets/metrics/__init__.py`

Add exports:
```python
from pipelines.assets.metrics.my_metric import (
    calculate_my_metric_asset,
    my_metric_data_check,
)
```

### Step 4: `pipelines/definitions.py`

```python
from pipelines.assets.metrics.my_metric import (
    calculate_my_metric_asset,
    my_metric_data_check,
)

# Add to asset_checks list:
asset_checks = [
    ...,
    my_metric_data_check,
]
```

Note: the asset itself is auto-discovered via `load_assets_from_modules()` if its module is already in the scanned list. Verify that `pipelines.assets.metrics` is included. If in doubt, add it explicitly to the assets list.

### Step 5: `pipelines/jobs/schedules.py`

```python
from pipelines.assets.metrics.my_metric import calculate_my_metric_asset

recalculate_my_metric_job = define_asset_job(
    name="recalculate_my_metric_job",
    selection=[calculate_my_metric_asset],
)

# Add to jobs = [...] at the bottom of the file
```

### Step 6: Migration — seed `metrics.definitions` and `metrics.calculations`

Create `db/migrations/versions/0032_seed_my_metric.py`:
```python
"""seed my_metric definitions and calculations"""
import uuid
from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    conn = op.get_bind()

    # Insert definition (metric group) — idempotent
    definition_id = str(uuid.uuid4())
    conn.execute(
        sa.text("""
            INSERT INTO metrics.definitions (id, metric_code)
            VALUES (:id, 'my_metric')
            ON CONFLICT (metric_code) DO NOTHING
        """).bindparams(id=definition_id)
    )

    # Insert calculation variant — resolved grain via JOIN — idempotent
    conn.execute(
        sa.text("""
            INSERT INTO metrics.calculations
                (id, definition_id, calc_code, grain_id, unit_code, uses_commitment_points)
            SELECT
                :id,
                d.id,
                'my_metric_days',
                g.id,
                'issue_count',
                false
            FROM metrics.definitions d
            CROSS JOIN metrics.grains g
            WHERE d.metric_code = 'my_metric'
              AND g.grain_code = 'issue'
            ON CONFLICT (calc_code) DO NOTHING
        """).bindparams(id=str(uuid.uuid4()))
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM metrics.calculations WHERE calc_code = 'my_metric_days'"))
    conn.execute(sa.text("DELETE FROM metrics.definitions WHERE metric_code = 'my_metric'"))
```

**Important:** Use `conn = op.get_bind()` + `conn.execute()` for parameterized queries in migrations. `op.execute(text(...), params_dict)` does NOT work for parameter binding — it ignores the second argument.

---

## context_json Usage

For metrics that need extra context stored alongside the value:
```python
{
    "context_json": {
        "assignee": "user@example.com",
        "components": ["frontend", "api"],
    }
}
```

Metabase can filter on `context_json->>'assignee'`. Do not store values that are already in `slice_value`.

---

## Commitment Rules (flow-based metrics only)

For metrics tied to board entry/exit columns:
```python
from pipelines.calculations.commitment_resolver import CommitmentRuleResolver

resolver = CommitmentRuleResolver(engine, project_id)
entry_col_id = resolver.entry_column_id
exit_col_id = resolver.exit_column_id
commitment_rule_id = resolver.rule_id  # store in fact_values row
```

Set `uses_commitment_points = true` in the migration if the metric requires this.
