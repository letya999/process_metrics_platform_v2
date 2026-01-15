# Refactor Plan: Migrate Metrics Calculation from SQL to Python (Polars)

**Date:** 2026-01-15
**Status:** Proposed
**Author:** AI Assistant (based on deep analysis)
**Estimated Effort:** 3-5 days of focused development

---

## Executive Summary

**Problem:** The current metrics calculation logic (Lead Time, Velocity, Throughput) is implemented as complex PostgreSQL Materialized Views (150+ line SQL queries with CTEs). This approach makes debugging, testing, and maintenance **extremely difficult**.

**Solution:** Migrate all business logic from SQL Materialized Views to **Python (Polars)**, while keeping the database schema simple (regular tables instead of MVs). Dagster will orchestrate Python-based calculation jobs.

**Benefits:**
- ✅ **Debuggable:** Set breakpoints, inspect DataFrames at any step.
- ✅ **Testable:** Write unit tests with mocked data.
- ✅ **Maintainable:** DRY principle (one function for "what is Done?"), reusable code.
- ✅ **Flexible:** Easy to add new metrics or change business rules.
- ✅ **Performance:** Polars is multithreaded and Rust-backed, handles 100k+ rows efficiently.

**Trade-offs:**
- ❌ Need to pull data from DB to memory (mitigated by Polars' efficiency).
- ❌ Migration effort (~3-5 days).

---

## Current State Analysis

### Architecture Overview

The current metrics system has **3 layers**:

1. **Raw Layer (Bronze):** `raw_jira.*` — dlt loads JSON from Jira API.
2. **Clean Layer (Silver):** `clean_jira.*` — Normalized tables (issues, sprints, changelog).
3. **Metrics Layer (Gold):** `metrics.*` — **Materialized Views** with embedded calculation logic.

### Complexity Breakdown

#### Fact Tables (as Materialized Views)
| Table | Lines of SQL | Purpose | Complexity |
|-------|--------------|---------|------------|
| `metrics.fact_velocity` | ~160 | Sprint Plan vs Fact (Story Points, Issues) | 🔴 Very High |
| `metrics.fact_velocity_slice` | ~70 | Velocity sliced by Issue Type | 🟠 High |
| `metrics.fact_lead_time` | ~120 | Lead Time using Board Column logic | 🔴 Very High |
| `metrics.fact_lead_time_slice` | ~40 | Lead Time sliced by Issue Type | 🟡 Medium |
| `metrics.fact_lead_time_bins` | ~15 | Histogram bins (aggregation) | 🟢 Low |
| `metrics.fact_lead_time_bins_slice` | ~20 | Histogram bins sliced | 🟡 Medium |

#### Presentation Views (Simple)
| View | Lines | Complexity |
|------|-------|------------|
| `mv_lead_time` | ~20 | 🟢 Just adds friendly column names |
| `mv_velocity` | ~20 | 🟢 Calculates completion % |
| `mv_throughput` | ~15 | 🟢 Groups by date |

**Total SQL LOC in Metrics:** ~480 lines (across 3 migrations: 0006, 0008, 0010).

### Key Business Logic Patterns

#### 1. **Velocity Calculation (Plan vs Fact)**

**Current SQL Logic (from `0010_fix_velocity_logic.py`):**

```sql
-- Step 1: Identify "Done" statuses from board configuration
end_statuses AS (
  SELECT DISTINCT s.id AS status_id, b.project_id
  FROM clean_jira.board_columns bc
  JOIN clean_jira.issue_statuses s ON ...
  WHERE bc.name ILIKE '%Done%'
)

-- Step 2: Get all issues ever in sprint
membership_base AS (
  SELECT DISTINCT ii.issue_id, ii.sprint_id AS iteration_id
  FROM clean_jira.sprint_issues ii
)

-- Step 3: Determine if issue was in sprint AT START (not added mid-sprint)
state_at_start AS (
  SELECT m.issue_id, m.iteration_id,
    (SELECT h.action FROM clean_jira.sprint_issues_changelog h
     WHERE h.changed_at <= sprint.start_date
     ORDER BY h.changed_at DESC LIMIT 1) AS action_at_start
  FROM membership_base m
)

-- Step 4: Planned = "added" before start OR created before start
planned_pairs AS (
  SELECT ... WHERE (action_at_start = 'added')
                OR (action_at_start IS NULL AND i.jira_created_at <= sprint.start_date)
)

-- Step 5: Extract Story Points (from custom fields or history)
planned_sp AS (
  SELECT p.issue_id, COALESCE(<complex JSONB parsing logic>) AS story_points
  FROM planned_pairs p
)

-- Step 6: Find "Done" issues (by history, resolution, or current status)
done_pairs AS (
  SELECT ... WHERE (resolved <= sprint.end_date) OR (status IN end_statuses) OR ...
)

-- Step 7: Aggregate
SELECT COUNT(planned), SUM(planned_sp), COUNT(done), SUM(done_sp)
FROM sprints LEFT JOIN planned LEFT JOIN done
GROUP BY sprint_id
```

**Pain Points:**
- 🔴 Nested CTEs (7 levels deep) make debugging impossible.
- 🔴 Story Points extraction has 3 fallback strategies (history, current value, estimate field) — hardcoded in SQL.
- 🔴 Logic for "what is planned?" appears **in 3 places** (base fact, slice, and different migrations).
- 🔴 Can't unit test "does this specific issue count as planned?"

#### 2. **Lead Time Calculation (Board Column Logic)**

**Current SQL Logic (from `0008_fix_schema_inconsistencies.py`):**

```sql
-- Step 1: Find "In Progress" and "Done" columns
points AS (
  SELECT start_column_id, end_column_id
  FROM board_columns
  WHERE name ILIKE '%In Progress%' OR name ILIKE '%Done%'
)

-- Step 2: Find when issue ENTERED end column (commitment_end)
end_event AS (
  SELECT issue_id, MIN(changed_at) AS end_at
  FROM issue_status_changelog
  WHERE to_status IN (SELECT status FROM end_column)
)

-- Step 3: Find when issue ENTERED start column (commitment_start)
start_event AS (
  SELECT issue_id, MIN(changed_at) AS start_at
  FROM issue_status_changelog
  WHERE to_status IN (SELECT status FROM start_column)
    AND changed_at <= end_at  -- Must be before end
)

-- Step 4: Calculate Lead Time
SELECT issue_id, EXTRACT(EPOCH FROM (end_at - start_at))/86400.0 AS lead_time_days
```

**Pain Points:**
- 🔴 Logic assumes boards are configured correctly (if not, silently fails).
- 🔴 Can't debug "why did this issue not get a Lead Time?" without manually running CTE-by-CTE.
- 🔴 No way to test edge cases (e.g., issue moved back and forth between columns).

#### 3. **Slices (Dimensional Analysis)**

**Current Approach:**
- Separate Materialized Views for each metric: `fact_velocity_slice`, `fact_lead_time_slice`.
- Each slice query **duplicates 80% of base logic** and adds a `GROUP BY issue_type`.

**Example from `0010_fix_velocity_logic.py`:**
```sql
CREATE MATERIALIZED VIEW metrics.fact_velocity_slice AS
WITH <copied logic from fact_velocity>
...
GROUP BY project_id, iteration_id, issue_type  -- Only difference!
```

**Pain Points:**
- 🔴 Copy-paste = double maintenance burden.
- 🔴 If base logic changes, must update **4 separate MVs** (velocity, velocity_slice, lead_time, lead_time_slice).

#### 4. **Bins (Histogram Buckets)**

**Current SQL:**
```sql
CREATE MATERIALIZED VIEW metrics.fact_lead_time_bins AS
SELECT project_id, CEIL(lead_time_days) AS bin_number, COUNT(*) AS tickets_count
FROM metrics.fact_lead_time
GROUP BY project_id, bin_number
```

**Pain Points:**
- 🟡 Relatively simple, but still requires separate MV refresh step.

---

## Historical Context: Python Scripts Exist!

**Discovery:** In the project root, there are **two standalone Python scripts**:
- `metrics_lead_time_recalculate.py` (18KB)
- `metrics_velocity_recalculate.py` (41KB)

**These scripts:**
- Were written for **Airflow** (old orchestrator).
- Use **raw SQL** (not Polars), but show **Python-based approach**.
- Contain **more sophisticated logic** than current MVs (e.g., handling custom fields by name, fallbacks).

**Key Insight:** The project **already tried** moving logic to Python, but:
1. Used raw SQL strings in Python (still not debuggable).
2. Airflow was replaced by Dagster.
3. MVs were introduced later (migration 0006) as a "simpler" solution.

**Lesson:** Moving to Python is correct, but we need **DataFrame-based logic**, not embedded SQL strings.

---

## Proposed Solution: Python (Polars) + Dagster

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Dagster Assets                       │
├─────────────────────────────────────────────────────────┤
│  1. calculate_velocity (Python)                         │
│     - Reads: clean_jira.sprints, issues, changelog     │
│     - Executes: Python business logic (Polars DF)      │
│     - Writes: metrics.fact_velocity (TABLE)            │
│                                                          │
│  2. calculate_lead_time (Python)                        │
│     - Reads: clean_jira.issues, boards, changelog      │
│     - Executes: Lead time logic (Polars DF)            │
│     - Writes: metrics.fact_lead_time (TABLE)           │
│                                                          │
│  3. refresh_presentation_views (SQL)                    │
│     - Refreshes: mv_lead_time, mv_velocity            │
│     - (Optional: Could also be Python)                 │
└─────────────────────────────────────────────────────────┘
```

### Key Principles

1. **Fact Tables = Regular Tables (not MVs):**
   - `metrics.fact_velocity` becomes a normal table.
   - Dagster assets **TRUNCATE + INSERT** on each run.

2. **Business Logic in Python Functions:**
   - Pure functions: `DataFrame → DataFrame`.
   - Example: `def is_issue_planned(issue_df, sprint_df, changelog_df) -> DataFrame`.

3. **DRY (Don't Repeat Yourself):**
   - Slices are generated by **same function** with `group_by(issue_type)`.
   - Bins are calculated via `pl.cut()` or `group_by(CEIL(lead_time))`.

4. **Presentation Views (Optional):**
   - Keep `mv_*` as simple SQL views for Metabase (or replace with dbt models).
   - Example: `SELECT *, (completed_sp / planned_sp * 100) AS completion_rate FROM fact_velocity`.

---

## Implementation Plan

### Phase 1: Setup & Infrastructure (Day 1)

#### 1.1 Add Polars Dependency
```bash
# pyproject.toml
[tool.pdm.dependencies]
polars = "^0.20.0"  # or latest
```

#### 1.2 Create Utility Module
**File:** `pipelines/utils/polars_db.py`
```python
import polars as pl
from sqlalchemy import Engine

def read_table(engine: Engine, query: str) -> pl.DataFrame:
    """Read SQL query results into Polars LazyFrame."""
    import pandas as pd
    pdf = pd.read_sql(query, engine)
    return pl.from_pandas(pdf)

def write_table(df: pl.DataFrame, engine: Engine, table: str, schema: str = "metrics"):
    """Write Polars DataFrame to PostgreSQL (TRUNCATE + INSERT)."""
    # Convert to Pandas for compatibility
    pdf = df.to_pandas()
    pdf.to_sql(table, engine, schema=schema, if_exists='replace', index=False, method='multi')
```

#### 1.3 Create Migration to Convert MVs → Tables
**File:** `db/migrations/versions/0011_convert_mvs_to_tables.py`
```python
"""Convert Materialized Views to regular Tables"""

def upgrade():
    # Drop all MVs
    op.execute("DROP MATERIALIZED VIEW IF EXISTS metrics.fact_velocity CASCADE;")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS metrics.fact_lead_time CASCADE;")
    # ... (all fact_* MVs)

    # Create empty tables with same schema
    op.execute("""
    CREATE TABLE metrics.fact_velocity (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        project_id UUID NOT NULL,
        iteration_id UUID NOT NULL,
        iteration_name TEXT,
        start_date DATE,
        end_date DATE,
        planned_story_points NUMERIC DEFAULT 0,
        completed_story_points NUMERIC DEFAULT 0,
        planned_issues INT DEFAULT 0,
        completed_issues INT DEFAULT 0,
        created_at TIMESTAMPTZ DEFAULT now()
    );
    """)
    # ... (similar for other fact tables)
```

---

### Phase 2: Velocity Refactor (Day 2-3)

#### 2.1 Create Business Logic Module
**File:** `pipelines/metrics/velocity.py`

```python
import polars as pl
from typing import List

def get_done_status_ids(boards_df: pl.DataFrame, board_columns_df: pl.DataFrame) -> List[str]:
    """
    Identify status IDs that represent "Done" based on board column configuration.

    Logic: Find columns named ~"Done" and extract their statuses.
    """
    done_columns = board_columns_df.filter(
        pl.col('name').str.to_lowercase().str.contains('done')
    )
    # Assume board_column_statuses already joined
    return done_columns['status_id'].unique().to_list()


def identify_planned_issues(
    sprint_issues_df: pl.DataFrame,
    sprint_changelog_df: pl.DataFrame,
    issues_df: pl.DataFrame,
    sprints_df: pl.DataFrame
) -> pl.DataFrame:
    """
    Determine which issues were "Planned" at sprint start.

    Business Rules:
    1. If issue was explicitly added BEFORE sprint start → Planned.
    2. If issue was created BEFORE sprint start AND never removed → Planned.
    3. If issue was added MID-sprint → NOT Planned (scope creep).

    Returns:
        DataFrame with columns: [issue_id, sprint_id, is_planned]
    """

    # Step 1: Join sprint_issues with sprints to get start_date
    membership = sprint_issues_df.join(
        sprints_df.select(['id', 'start_date']),
        left_on='sprint_id',
        right_on='id',
        how='left'
    )

    # Step 2: For each (issue, sprint), find LAST action <= start_date
    state_at_start = (
        membership
        .join(sprint_changelog_df, on=['issue_id', 'sprint_id'], how='left')
        .filter(pl.col('changed_at') <= pl.col('start_date'))
        .sort('changed_at', descending=True)
        .group_by(['issue_id', 'sprint_id'])
        .first()  # Last action before start
    )

    # Step 3: Determine if planned
    planned = state_at_start.with_columns([
        (
            (pl.col('action') == 'added')  # Explicitly added
            |
            (  # OR: No history AND created before start
                pl.col('action').is_null() &
                (pl.col('jira_created_at') <= pl.col('start_date'))
            )
        ).alias('is_planned')
    ])

    return planned.select(['issue_id', 'sprint_id', 'is_planned'])


def extract_story_points(
    planned_df: pl.DataFrame,
    field_values_df: pl.DataFrame,
    field_keys_df: pl.DataFrame
) -> pl.DataFrame:
    """
    Extract Story Points for planned issues.

    Fallback strategy:
    1. Try custom field "Story Points" (by name).
    2. Try customfield_10036, customfield_10016.
    3. Default to 0.

    Returns:
        DataFrame with: [issue_id, sprint_id, story_points]
    """
    # Identify Story Points field ID
    sp_fields = field_keys_df.filter(
        (pl.col('external_key').is_in(['customfield_10036', 'customfield_10016', 'story_points']))
        | (pl.col('name').str.to_lowercase().str.contains('story point'))
    )

    # Join planned issues with field values
    sp_values = (
        planned_df
        .join(field_values_df, on='issue_id', how='left')
        .join(sp_fields, left_on='field_key_id', right_on='id', how='inner')
        .select([
            'issue_id',
            'sprint_id',
            pl.col('json_value').cast(pl.Float64).fill_null(0).alias('story_points')
        ])
        .group_by(['issue_id', 'sprint_id'])
        .agg(pl.col('story_points').max())  # Take max if multiple fields
    )

    return sp_values


def identify_completed_issues(
    planned_df: pl.DataFrame,
    issues_df: pl.DataFrame,
    status_changelog_df: pl.DataFrame,
    done_status_ids: List[str],
    sprints_df: pl.DataFrame
) -> pl.DataFrame:
    """
    Determine which planned issues were completed by sprint end.

    Business Rules:
    1. Issue resolved_at <= sprint.end_date → Completed.
    2. Issue transitioned to Done status <= sprint.end_date → Completed.
    3. Current status is Done AND sprint ended → Completed.

    Returns:
        DataFrame with: [issue_id, sprint_id, is_completed]
    """
    # Join planned with sprint end dates
    with_end_dates = planned_df.join(
        sprints_df.select(['id', 'end_date']),
        left_on='sprint_id',
        right_on='id'
    )

    # Strategy 1: Resolved by end date
    resolved_by_end = (
        with_end_dates
        .join(issues_df.select(['id', 'jira_resolved_at']), left_on='issue_id', right_on='id')
        .filter(
            pl.col('jira_resolved_at').is_not_null() &
            (pl.col('jira_resolved_at') <= pl.col('end_date'))
        )
        .select(['issue_id', 'sprint_id'])
        .with_columns(pl.lit(True).alias('is_completed'))
    )

    # Strategy 2: Transitioned to Done by end date (from changelog)
    done_by_changelog = (
        with_end_dates
        .join(status_changelog_df, on='issue_id')
        .filter(
            pl.col('to_status_id').is_in(done_status_ids) &
            (pl.col('changed_at') <= pl.col('end_date'))
        )
        .select(['issue_id', 'sprint_id'])
        .unique()
        .with_columns(pl.lit(True).alias('is_completed'))
    )

    # Combine strategies (UNION)
    completed = pl.concat([resolved_by_end, done_by_changelog]).unique()

    return completed


def calculate_velocity_facts(
    sprints_df: pl.DataFrame,
    sprint_issues_df: pl.DataFrame,
    sprint_changelog_df: pl.DataFrame,
    issues_df: pl.DataFrame,
    field_values_df: pl.DataFrame,
    field_keys_df: pl.DataFrame,
    status_changelog_df: pl.DataFrame,
    boards_df: pl.DataFrame,
    board_columns_df: pl.DataFrame
) -> pl.DataFrame:
    """
    Main orchestration function: Calculate Velocity facts.

    Returns:
        DataFrame ready to insert into metrics.fact_velocity
    """
    # Step 1: Identify Done statuses
    done_status_ids = get_done_status_ids(boards_df, board_columns_df)

    # Step 2: Identify planned issues
    planned = identify_planned_issues(
        sprint_issues_df, sprint_changelog_df, issues_df, sprints_df
    )

    # Step 3: Extract story points for planned
    planned_with_sp = planned.join(
        extract_story_points(planned, field_values_df, field_keys_df),
        on=['issue_id', 'sprint_id'],
        how='left'
    ).fill_null({'story_points': 0})

    # Step 4: Identify completed issues
    completed = identify_completed_issues(
        planned, issues_df, status_changelog_df, done_status_ids, sprints_df
    )

    # Step 5: Aggregate by sprint
    velocity_agg = (
        sprints_df
        .join(
            planned_with_sp.group_by('sprint_id').agg([
                pl.count('issue_id').alias('planned_issues'),
                pl.sum('story_points').alias('planned_story_points')
            ]),
            left_on='id',
            right_on='sprint_id',
            how='left'
        )
        .join(
            planned_with_sp
            .join(completed, on=['issue_id', 'sprint_id'], how='inner')
            .group_by('sprint_id').agg([
                pl.count('issue_id').alias('completed_issues'),
                pl.sum('story_points').alias('completed_story_points')
            ]),
            left_on='id',
            right_on='sprint_id',
            how='left'
        )
        .fill_null(0)
        .select([
            pl.lit(None).alias('id'),  # Will be auto-generated UUID
            pl.col('project_id'),
            pl.col('id').alias('iteration_id'),
            pl.col('name').alias('iteration_name'),
            pl.col('start_date'),
            pl.col('end_date'),
            pl.col('planned_story_points'),
            pl.col('completed_story_points'),
            pl.col('planned_issues'),
            pl.col('completed_issues'),
        ])
    )

    return velocity_agg
```

#### 2.2 Create Dagster Asset
**File:** `pipelines/assets/metrics/velocity.py` (replace existing)

```python
from typing import Any
from dagster import AssetExecutionContext, asset
from pipelines.resources.database import DatabaseResource
from pipelines.utils.polars_db import read_table, write_table
from pipelines.metrics import velocity as velocity_logic

@asset(
    group_name="metrics",
    deps=[
        "clean_jira_issues",
        "clean_jira_sprints",
        "clean_jira_boards",
        "clean_jira_issue_status_changelog",
        "clean_jira_sprint_issues",
        "clean_jira_sprint_issues_changelog",
    ],
    description="Calculate Velocity facts using Polars (Python)",
    compute_kind="python",
)
def calculate_velocity(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    """
    Calculate Velocity metrics (Plan vs Fact) for all sprints.

    This replaces the SQL Materialized View with Python logic.
    """
    engine = database.get_engine()

    context.log.info("Loading data from clean_jira schema...")

    # Load all required tables into Polars DataFrames
    sprints_df = read_table(engine, "SELECT * FROM clean_jira.sprints WHERE start_date IS NOT NULL")
    sprint_issues_df = read_table(engine, "SELECT * FROM clean_jira.sprint_issues")
    sprint_changelog_df = read_table(engine, "SELECT * FROM clean_jira.sprint_issues_changelog")
    issues_df = read_table(engine, "SELECT id, project_id, jira_created_at, jira_resolved_at, status_id FROM clean_jira.issues")
    field_values_df = read_table(engine, "SELECT * FROM clean_jira.field_values")
    field_keys_df = read_table(engine, "SELECT * FROM clean_jira.field_keys")
    status_changelog_df = read_table(engine, "SELECT * FROM clean_jira.issue_status_changelog")
    boards_df = read_table(engine, "SELECT * FROM clean_jira.boards")
    board_columns_df = read_table(engine, """
        SELECT bc.*, bcs.status_id
        FROM clean_jira.board_columns bc
        JOIN clean_jira.board_column_statuses bcs ON bcs.board_column_id = bc.id
    """)

    context.log.info(f"Loaded {len(sprints_df)} sprints, {len(issues_df)} issues")

    # Calculate velocity facts
    context.log.info("Calculating velocity facts...")
    velocity_df = velocity_logic.calculate_velocity_facts(
        sprints_df=sprints_df,
        sprint_issues_df=sprint_issues_df,
        sprint_changelog_df=sprint_changelog_df,
        issues_df=issues_df,
        field_values_df=field_values_df,
        field_keys_df=field_keys_df,
        status_changelog_df=status_changelog_df,
        boards_df=boards_df,
        board_columns_df=board_columns_df
    )

    context.log.info(f"Calculated velocity for {len(velocity_df)} sprints")

    # Write to database
    context.log.info("Writing to metrics.fact_velocity...")
    write_table(velocity_df, engine, table='fact_velocity', schema='metrics')

    return {
        "status": "success",
        "sprints_processed": len(velocity_df),
        "total_planned_issues": velocity_df['planned_issues'].sum(),
        "total_completed_issues": velocity_df['completed_issues'].sum()
    }
```

#### 2.3 Create Unit Tests
**File:** `tests/unit/test_velocity_logic.py`

```python
import polars as pl
import pytest
from pipelines.metrics.velocity import identify_planned_issues

def test_issue_added_before_start_is_planned():
    """Test that issue added before sprint start is marked as planned."""
    sprint_issues = pl.DataFrame({
        'issue_id': ['ISS-1'],
        'sprint_id': ['SPRINT-1']
    })

    sprint_changelog = pl.DataFrame({
        'issue_id': ['ISS-1'],
        'sprint_id': ['SPRINT-1'],
        'action': ['added'],
        'changed_at': [pl.datetime(2024, 1, 1, 8, 0)]
    })

    issues = pl.DataFrame({
        'id': ['ISS-1'],
        'jira_created_at': [pl.datetime(2023, 12, 1)]
    })

    sprints = pl.DataFrame({
        'id': ['SPRINT-1'],
        'start_date': [pl.date(2024, 1, 2)]
    })

    result = identify_planned_issues(sprint_issues, sprint_changelog, issues, sprints)

    assert result.filter(pl.col('issue_id') == 'ISS-1')['is_planned'][0] == True


def test_issue_added_mid_sprint_is_not_planned():
    """Test that issue added AFTER sprint start is NOT planned (scope creep)."""
    sprint_issues = pl.DataFrame({
        'issue_id': ['ISS-2'],
        'sprint_id': ['SPRINT-1']
    })

    sprint_changelog = pl.DataFrame({
        'issue_id': ['ISS-2'],
        'sprint_id': ['SPRINT-1'],
        'action': ['added'],
        'changed_at': [pl.datetime(2024, 1, 5, 10, 0)]  # Added mid-sprint
    })

    issues = pl.DataFrame({
        'id': ['ISS-2'],
        'jira_created_at': [pl.datetime(2024, 1, 3)]
    })

    sprints = pl.DataFrame({
        'id': ['SPRINT-1'],
        'start_date': [pl.date(2024, 1, 2)]
    })

    result = identify_planned_issues(sprint_issues, sprint_changelog, issues, sprints)

    # Issue added AFTER start_date → NOT planned
    assert result.filter(pl.col('issue_id') == 'ISS-2')['is_planned'][0] == False
```

**Run tests:**
```bash
pytest tests/unit/test_velocity_logic.py -v
```

---

### Phase 3: Lead Time Refactor (Day 3-4)

#### 3.1 Create Business Logic Module
**File:** `pipelines/metrics/lead_time.py`

```python
import polars as pl

def identify_commitment_points(
    boards_df: pl.DataFrame,
    board_columns_df: pl.DataFrame
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """
    Identify "In Progress" (start) and "Done" (end) columns from board configuration.

    Returns:
        (start_columns_df, end_columns_df)
    """
    start_columns = board_columns_df.filter(
        pl.col('name').str.to_lowercase().str.contains('in progress')
    )

    end_columns = board_columns_df.filter(
        pl.col('name').str.to_lowercase().str.contains('done')
    )

    return start_columns, end_columns


def calculate_lead_time_per_issue(
    issues_df: pl.DataFrame,
    status_changelog_df: pl.DataFrame,
    start_status_ids: list[str],
    end_status_ids: list[str]
) -> pl.DataFrame:
    """
    Calculate Lead Time (commitment_start → commitment_end) for each issue.

    Business Rules:
    1. commitment_start = FIRST time issue entered "In Progress" column.
    2. commitment_end = FIRST time issue entered "Done" column (after start).
    3. Lead Time = end - start (in days).

    Returns:
        DataFrame: [issue_id, project_id, commitment_start_at, commitment_end_at, lead_time_days]
    """
    # Find first "In Progress" transition per issue
    start_events = (
        status_changelog_df
        .filter(pl.col('to_status_id').is_in(start_status_ids))
        .group_by('issue_id')
        .agg(pl.col('changed_at').min().alias('commitment_start_at'))
    )

    # Find first "Done" transition per issue (AFTER start)
    end_events = (
        status_changelog_df
        .join(start_events, on='issue_id')
        .filter(
            pl.col('to_status_id').is_in(end_status_ids) &
            (pl.col('changed_at') > pl.col('commitment_start_at'))
        )
        .group_by('issue_id')
        .agg(pl.col('changed_at').min().alias('commitment_end_at'))
    )

    # Combine
    lead_time = (
        issues_df
        .join(start_events, left_on='id', right_on='issue_id', how='left')
        .join(end_events, left_on='id', right_on='issue_id', how='left')
        .filter(
            pl.col('commitment_start_at').is_not_null() &
            pl.col('commitment_end_at').is_not_null()
        )
        .with_columns([
            (
                (pl.col('commitment_end_at') - pl.col('commitment_start_at'))
                .dt.total_seconds() / 86400.0
            ).alias('lead_time_days')
        ])
        .select([
            pl.col('id').alias('issue_id'),
            pl.col('project_id'),
            'commitment_start_at',
            'commitment_end_at',
            'lead_time_days'
        ])
    )

    return lead_time


def calculate_histogram_bins(lead_time_df: pl.DataFrame) -> pl.DataFrame:
    """
    Create histogram bins (1 day, 2 days, 3 days, etc.).

    Returns:
        DataFrame: [project_id, bin_number, tickets_count]
    """
    bins_df = (
        lead_time_df
        .with_columns([
            pl.col('lead_time_days').ceil().cast(pl.Int32).alias('bin_number')
        ])
        .group_by(['project_id', 'bin_number'])
        .agg(pl.count().alias('tickets_count'))
    )

    return bins_df
```

#### 3.2 Create Dagster Asset
(Similar to Velocity, omitted for brevity)

---

### Phase 4: Slices & Bins (Day 4)

**Key Insight:** With Polars, slices are **trivial**. Just add `.group_by()`.

**Example:**
```python
def calculate_velocity_slice_by_issue_type(velocity_df: pl.DataFrame, issues_df: pl.DataFrame) -> pl.DataFrame:
    """
    Slice velocity by issue type (same logic, just group by type).
    """
    return (
        velocity_df
        .join(issues_df.select(['id', 'type_name']), left_on='issue_id', right_on='id')
        .group_by(['project_id', 'sprint_id', 'type_name'])
        .agg([
            pl.sum('planned_issues'),
            pl.sum('planned_story_points'),
            pl.sum('completed_issues'),
            pl.sum('completed_story_points')
        ])
    )
```

**No need for separate SQL MVs!** Just call this function in the same asset and write to `fact_velocity_slice` table.

---

### Phase 5: Cleanup & Migration (Day 5)

#### 5.1 Remove Old Logic
- Delete migrations: `0006`, `0008`, `0010` (keep schema definitions, remove MV logic).
- Delete old Python scripts: `metrics_velocity_recalculate.py`, `metrics_lead_time_recalculate.py`.

#### 5.2 Update Documentation
- Update `CLAUDE.md`: Remove "Materialized Views" section, add "Python Metrics Calculation".
- Update `README.md`: Mention Polars as dependency.

#### 5.3 Run End-to-End Test
```bash
# Sync data
make dev
docker-compose exec dagster dagster job execute -j jira_sync_job

# Calculate metrics
docker-compose exec dagster dagster asset materialize -s calculate_velocity
docker-compose exec dagster dagster asset materialize -s calculate_lead_time

# Verify in Metabase
```

---

## Comparison: Before vs After

| Aspect | Before (SQL MVs) | After (Python/Polars) |
|--------|------------------|----------------------|
| **Debugging** | ❌ Print CTE results manually | ✅ `print(df)`, breakpoints |
| **Testing** | ❌ No unit tests | ✅ pytest with mocked DataFrames |
| **Code Reuse** | ❌ Copy-paste for slices | ✅ DRY: one function + `.group_by()` |
| **Performance** | ✅ In-DB (fast) | ✅ Polars (Rust, multithreaded) |
| **Maintainability** | 🔴 480 lines SQL across 3 migrations | 🟢 ~300 lines modular Python |
| **Extensibility** | ❌ New slice = new MV | ✅ New slice = add column to `group_by` |

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| **Performance:** Pulling data to memory | • Polars is lazy (only loads needed columns). <br> • For 100k issues, memory usage ~500MB. <br> • If scales to millions: Use chunking or Spark. |
| **Learning Curve:** Team unfamiliar with Polars | • Polars syntax is similar to Pandas. <br> • Provide training session + examples. |
| **Migration Bugs:** New logic differs from old | • Run both systems in parallel for 1 sprint. <br> • Compare results, fix discrepancies. |
| **Rollback Complexity:** Hard to undo | • Keep migration `0012_rollback_to_mvs.py` ready. <br> • Feature flag: `USE_PYTHON_METRICS=true`. |

---

## Success Criteria

- ✅ All tests pass (`pytest tests/unit/test_velocity_logic.py`).
- ✅ Velocity metrics match SQL version (\<5% variance).
- ✅ Lead Time metrics calculated correctly.
- ✅ Dagster job completes in \<5 min for 10k issues.
- ✅ Metabase dashboards show correct data.

---

## Next Steps

1. **Review this plan** with team.
2. **Spike:** Implement Phase 1 + 2.1 (Velocity logic only) on a branch.
3. **Validate:** Compare results with current SQL MVs.
4. **Full Migration:** Implement remaining phases.
5. **Deploy:** Merge to main, run migration.

---

## References

- **Polars Documentation:** https://pola-rs.github.io/polars/
- **Current Migrations:**
  - `db/migrations/versions/0006_add_metrics_slice_tables.py`
  - `db/migrations/versions/0008_fix_schema_inconsistencies.py`
  - `db/migrations/versions/0010_fix_velocity_logic.py`
- **Old Python Scripts (for reference):**
  - `metrics_velocity_recalculate.py`
  - `metrics_lead_time_recalculate.py`

---

**End of Refactor Plan**
