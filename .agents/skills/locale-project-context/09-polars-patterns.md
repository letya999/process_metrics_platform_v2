---
name: polars-patterns
description: Project-specific Polars patterns for pre-1.0 API (>=0.20.0,<1.0.0). Empty DataFrame guards, null handling, groupby, LazyFrame thresholds.
triggers:
  - "polars"
  - "dataframe"
  - "pl."
  - "lazy frame"
  - "groupby"
  - "group_by"
  - "map_elements"
context:
  - agent.md
---

# Skill: Polars Patterns

Project-specific Polars patterns. Version constraint: `>=0.20.0,<1.0.0`.
See also installed marketplace skill `polars` (silvainfm/claude-skills@polars) for API reference.

---

## Version Constraint

This project uses Polars **pre-1.0** (`<1.0.0`). Polars 1.0 introduced breaking API changes.

Key differences from 1.0+ to watch for:
- `pl.Series.to_list()` behavior with nulls differs slightly
- `LazyFrame.collect()` error handling changed
- Some `map_elements` vs `apply` naming finalized in 1.0

If you see a Polars snippet online, verify it works in 0.20–0.29 range.

---

## Loading Data

Always use `read_table()`, not raw Polars DB functions. Always pass a full SELECT query:
```python
from pipelines.utils.polars_db import read_table

df = read_table(engine, "SELECT * FROM clean_jira.issues")
```

For Polars operations on the loaded data, immediately chain type casts for reliability:
```python
df = read_table(engine, "SELECT * FROM clean_jira.issues").with_columns([
    pl.col("created_at").cast(pl.Datetime("us", "UTC")),
    pl.col("story_points").cast(pl.Float64),
])
```

---

## Null Handling

Jira data is messy. Assume every numeric column can have nulls.

```python
# Story points: always fill_null before aggregation
sp_sum = df.select(
    pl.col("story_points").fill_null(0.0).sum()
).item()

# Or use drop_nulls before groupby
result = df.drop_nulls(subset=["story_points", "completed_at"])
```

---

## Wide → Long Transform (fact_values pattern)

The most common transform in metric calculations. All metrics end up in long format.

```python
# Wide: one row per sprint, multiple metric columns
wide_df = pl.DataFrame({
    "sprint_id": ["s1", "s2"],
    "project_id": ["p1", "p1"],
    "planned_sp": [20.0, 15.0],
    "completed_sp": [18.0, 12.0],
})

# Long: one row per sprint × metric
long_df = wide_df.melt(
    id_vars=["sprint_id", "project_id"],
    value_vars=["planned_sp", "completed_sp"],
    variable_name="calc_code",
    value_name="value",
)
# Result: 4 rows with columns sprint_id, project_id, calc_code, value
```

---

## Date Calculations

```python
from datetime import UTC

# Days between two timestamps
df = df.with_columns(
    (
        (pl.col("completed_at") - pl.col("created_at"))
        .dt.total_seconds() / 86400
    ).alias("lead_time_days")
)

# Convert date to time_id (YYYYMMDD int)
df = df.with_columns(
    pl.col("completed_at")
    .dt.strftime("%Y%m%d")
    .cast(pl.Int32)
    .alias("time_id")
)

# Filter to date range
df = df.filter(
    pl.col("completed_at").dt.date() >= pl.lit(start_date)
)
```

---

## GroupBy Aggregations

```python
# Velocity per sprint
velocity = (
    sprint_issues
    .filter(pl.col("is_active"))
    .groupby("sprint_id")
    .agg([
        pl.col("story_points").sum().alias("planned_sp"),
        pl.col("issue_key").count().alias("planned_count"),
    ])
)

# Lead time percentiles
percentiles = (
    issues
    .filter(pl.col("lead_time_days").is_not_null())
    .groupby("project_id")
    .agg([
        pl.col("lead_time_days").mean().alias("mean_days"),
        pl.col("lead_time_days").quantile(0.5).alias("p50_days"),
        pl.col("lead_time_days").quantile(0.85).alias("p85_days"),
    ])
)
```

---

## Joining DataFrames

```python
# Join issues with their sprint data
issues_with_sprint = issues.join(
    sprint_issues.select(["issue_key", "sprint_id", "is_active"]),
    on="issue_key",
    how="left",
)

# Join changelog with issues to get project_id
changelog_enriched = changelog.join(
    issues.select(["id", "project_id", "key"]),
    left_on="issue_id",
    right_on="id",
    how="inner",
)
```

---

## Polars Struct Columns (CRITICAL)

dlt sometimes produces nested `Struct` typed columns from JSON. These CANNOT be written to PostgreSQL via the pandas bridge without serialization.

```python
# Detect and serialize Struct columns before any DB write
import json

def serialize_struct_cols(df: pl.DataFrame) -> pl.DataFrame:
    struct_cols = [
        col for col, dtype in zip(df.columns, df.dtypes)
        if isinstance(dtype, pl.Struct)
    ]
    if not struct_cols:
        return df
    return df.with_columns([
        pl.col(c).map_elements(
            lambda v: json.dumps(v) if v is not None else None,
            return_dtype=pl.Utf8,
        )
        for c in struct_cols
    ])
```

---

## Empty DataFrame Guards

Every calculation function must handle empty input:

```python
def calculate_velocity(sprint_issues: pl.DataFrame, sprints: pl.DataFrame) -> pl.DataFrame:
    if sprint_issues.is_empty() or sprints.is_empty():
        return pl.DataFrame(schema={
            "sprint_id": pl.Utf8,
            "calc_code": pl.Utf8,
            "value": pl.Float64,
        })
    # ... normal logic
```

Return an empty DataFrame with the correct schema, not None. Downstream code must not need to check for None.

---

## LazyFrame for Large Datasets

For tables with >100k rows (issue_status_changelog, field_value_changelog), use LazyFrame:

```python
result = (
    pl.scan_csv(...)   # or use collect() from scan
    .filter(pl.col("project_id") == project_id)
    .groupby("status_name")
    .agg(pl.col("days").sum())
    .collect()         # execute the lazy plan
)
```

For typical project sizes (<50k issues), eager DataFrames are fine.

---

## Polars ↔ Python Interop

```python
# DataFrame → list of dicts (for SQL executemany)
rows = df.to_dicts()

# Single value extraction
value = df.filter(pl.col("key") == "X")["value"].item()

# Column to Python list
sprint_ids = df["sprint_id"].unique().to_list()

# Check row count
if df.shape[0] == 0: ...     # preferred over df.is_empty() for clarity
if len(df) == 0: ...         # also valid
```

---

## Common Pitfalls

```python
# WRONG: Using pandas-style inplace
df["new_col"] = df["old_col"] * 2  # raises TypeError

# CORRECT: Polars is immutable
df = df.with_columns(
    (pl.col("old_col") * 2).alias("new_col")
)

# WRONG: Comparing nullable column with == None
df.filter(pl.col("completed_at") == None)  # doesn't work

# CORRECT: Use is_null()
df.filter(pl.col("completed_at").is_null())

# WRONG: pandas-style df.groupby (deprecated in pre-1.0 versions)
# CORRECT: use group_by (no underscore in newer pre-1.0, or groupby in older)
# Check your exact version behavior — use .groupby() for 0.20.x compatibility
```

---

## Marketplace Skill Reference

For API reference and advanced Polars patterns:
```
/polars  (silvainfm/claude-skills@polars)
```
