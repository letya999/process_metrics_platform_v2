# Plan: Fix Code Review Issues from Metrics Expansion
**Date:** 2026-03-21
**Fixes for:** implementation from plan_metrics_expansion_21_new_20260321.md

---

## CRITICAL Fixes (must fix, will crash in production)

### Fix F-001: `iteration_id` KeyError in sprint_health calculations

**Files:** `pipelines/calculations/sprint_health.py`, `pipelines/assets/metrics/sprint_health.py`

**Problem:** `sprints_df` from `clean_jira.sprints` has column `id`, NOT `iteration_id`. Code does `sprint["iteration_id"]` after `to_dicts()` — KeyError at runtime.

**Fix in `pipelines/calculations/sprint_health.py`:**
- In `calculate_sprint_burndown()`: every `sprint["iteration_id"]` → `sprint["id"]`
- In `calculate_activation_velocity()`: every `sprint["iteration_id"]` → `sprint["id"]`
- The burndown result column alias is fine as `"iteration_id"` (it's the output alias)
- Also `sprint["complete_date"]` may not exist — use `sprint.get("complete_date") or sprint.get("end_date")`

**Fix in `tests/unit/test_sprint_health.py`:**
- Remove the fake `"iteration_id"` column from sprints test fixtures
- The sprints fixture should only have `id`, `project_id`, `name`, `start_date`, `end_date`

---

### Fix F-002: `pl.concat` schema mismatch in sprint_health asset

**File:** `pipelines/assets/metrics/sprint_health.py`, `pipelines/assets/metrics/flow_dynamics.py`

**Problem:** When `field_value_sprint_pct` settings exist, it produces DataFrames with `settings_id` column, but all other metric DataFrames don't have `settings_id`. `pl.concat` fails with SchemaError.

**Fix:** In `sprint_health.py`, before appending `facts_field_pct` to `all_facts`, add `settings_id` as `pl.lit(None, dtype=pl.Utf8)` to ALL other fact DataFrames (scope changes, spillover, burndown, activation, unestimated), OR use `pl.concat(all_facts, how="diagonal_relaxed")` which auto-fills missing columns with null.

Simplest fix: Use `pl.concat([f for f in all_facts if not f.is_empty()], how="diagonal_relaxed")` in sprint_health.py line ~257.

Same fix needed in `flow_dynamics.py` if `daily_status_entry_count` vs `field_change_count` have different columns.

---

### Fix F-003: Missing `project_id` in flow_dynamics calculations

**File:** `pipelines/calculations/flow_dynamics.py`

**Problem:** `calculate_daily_status_entry` groups by `"project_id"` but `issue_status_changelog` has no `project_id` column. The cross-join with sprints only adds `id, start_date, end_date`.

**Fix:** In `calculate_daily_status_entry`, change the sprints select to include `project_id`:
```python
sprints_df.select(["id", "project_id", "start_date", "end_date"])
```

**Also fix `calculate_field_change_count`:** Same issue — `sprints_df.select(["id", "start_date", "end_date"])` needs to include `project_id`.

**Fix the tests:** Remove manually injected `project_id` from `status_changelog_df` in test fixtures. `project_id` should come from the sprint join, not the changelog.

---

### Fix F-005: SQL injection via f-strings in all new assets

**Files:** All 8 new asset files: `sprint_health.py`, `flow_dynamics.py`, `input_flow.py`, `quality.py`, `delivery.py`, `cycle_time_ext.py`, `waste.py`, `estimation.py`, `aging_extended.py`

**Problem:** All new assets build SQL queries with f-strings like:
```python
read_table(engine, f"SELECT ... WHERE cs.target_calculation_id = '{calc_id}' ...")
```

**Fix:** Replace ALL f-string SQL queries with parameterized queries:
```python
read_table(engine, """
    SELECT cs.* FROM metrics.calculation_settings cs
    WHERE cs.target_calculation_id = :calc_id AND cs.enabled = true
""", params={"calc_id": calc_id})
```

Search for ALL occurrences of `f"""` or `f"SELECT` in the new asset files and replace with parameterized versions. The `read_table()` function in `polars_db.py` already supports `params` dict.

---

### Fix F-006: Hardcoded `time_id = 20260321` in estimation asset

**File:** `pipelines/assets/metrics/estimation.py`

**Problem:** `pl.lit(20260321)` hardcoded date makes data stale after deployment.

**Fix:**
```python
from datetime import date
today_id = int(date.today().strftime("%Y%m%d"))
# ...
pl.lit(today_id).cast(pl.Int32).alias("time_id")
# ...
write_fact_values(..., time_id_start=today_id, time_id_end=today_id)
```

Check if same hardcoded date exists in ANY other new asset files and fix those too.

---

## HIGH Fixes (significant logic or correctness issues)

### Fix F-007: Brittle datetime `.date()` on dict values

**Files:** `pipelines/calculations/sprint_health.py` (lines ~197-198, ~288-289), `pipelines/calculations/delivery.py` (lines ~55-56)

**Problem:** `sprint["start_date"].date()` assumes datetime object from Polars. Can be string when read via pandas fallback path.

**Fix:** Add defensive parsing:
```python
from datetime import date, datetime

def _to_date(v):
    if isinstance(v, date):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        return date.fromisoformat(v[:10])
    return v

start_date = _to_date(sprint["start_date"])
end_date = _to_date(sprint.get("complete_date") or sprint.get("end_date"))
```

Add this helper at the top of `sprint_health.py` and `delivery.py`.

---

### Fix F-009: Unbounded loop in delivery burnup

**File:** `pipelines/calculations/delivery.py`

**Problem:** Daily loop from earliest issue creation to today() can produce thousands of rows per version.

**Fix:** Cap the date range and use vectorized Polars operations:
1. Limit date range: `start_date = max(v_issues_data["created_at"].min().date(), date.today() - timedelta(days=730))` (2-year cap)
2. Better: Use vectorized cumulative approach with `pl.date_range` instead of Python while loop:

```python
import polars as pl
from datetime import date, timedelta

# Generate date range as Polars Series
dates = pl.date_range(start_date, end_date, "1d", eager=True)

# Vectorized scope: count issues created on or before each date
# Vectorized done: count issues with done_date on or before each date
# Use cross join with date range, then filter and aggregate
```

Or at minimum add a hard cap: if date range > 365 days, only use last 365 days.

---

### Fix F-011: Timezone mismatch in stale_days and blocked_time

**File:** `pipelines/calculations/aging.py` (new functions)

**Problem:** `pl.lit(now_date)` where `now_date = datetime.now(timezone.utc)` but `updated_at` column may be timezone-naive.

**Fix:** Strip timezone from `now_date` to match the column:
```python
from datetime import datetime, timezone, timedelta

now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
result = open_issues.with_columns(
    ((pl.lit(now_naive) - pl.col("updated_at")).dt.total_seconds() / 86400.0).round(2).alias("stale_days")
)
```

Or cast the column: `.dt.replace_time_zone(None)` if needed.

---

### Fix F-012: Column name inconsistency (value vs json_value) in estimation

**File:** `pipelines/calculations/estimation.py`, `pipelines/assets/metrics/estimation.py`

**Problem:** Estimation uses `value` column alias but project convention is `json_value`.

**Fix:**
1. In `estimation.py` asset: change SQL alias from `json_value::text as value` to `json_value::text as json_value`
2. In `pipelines/calculations/estimation.py`: change `pl.col("value")` to `pl.col("json_value")`
3. Update `test_estimation.py` fixtures: column name `"value"` → `"json_value"` in field_values DataFrames

---

### Fix F-013: Division by zero in field_value_sprint_pct

**File:** `pipelines/calculations/sprint_health.py`

**Problem:** `(match_count / total_count * 100).fill_null(0.0)` does not guard against `total_count = 0` (produces inf/NaN).

**Fix:**
```python
(pl.when(pl.col("total_count") > 0)
   .then(pl.col("match_count") / pl.col("total_count") * 100)
   .otherwise(pl.lit(0.0))
).alias("field_pct")
```

---

### Fix F-015: Empty changelog passed to `identify_sprint_final_scope` in unestimated_closed

**File:** `pipelines/calculations/sprint_health.py`

**Problem:** `calculate_unestimated_closed` calls `identify_sprint_final_scope(sprint_issues_df, pl.DataFrame(), issues_df)` — the empty changelog means removed issues are counted as in-scope.

**Fix:** The function signature should accept `sprint_changelog_df` as a parameter and pass it through:
```python
def calculate_unestimated_closed(sprints_df, sprint_issues_df, sprint_changelog_df, issues_df, issue_status_changelog_df, done_status_ids, field_values_df, sp_field_key_id):
    # ...
    final_scope = identify_sprint_final_scope(sprint_issues_df, sprint_changelog_df, issues_df)
```

Update the call site in `sprint_health.py` asset to pass `sprint_changelog_df`.
Update test to pass a `sprint_changelog_df` fixture (can be empty DataFrame with correct schema).

---

## MEDIUM Fixes

### Fix F-014: Move inline imports to module top in sprint_health.py

**File:** `pipelines/calculations/sprint_health.py`

**Problem:** `extract_story_points` and `identify_completed_issues` are imported inside function bodies.

**Fix:** Move to top of module with other velocity imports:
```python
from pipelines.calculations.velocity import (
    determine_story_points_at_date,
    identify_sprint_commitment,
    extract_story_points,
    identify_completed_issues,
    identify_sprint_final_scope,
)
```

---

### Fix F-016: Migration safety for existing definitions

**File:** `db/migrations/versions/0026_add_expanded_metrics.py`

**Problem:** The calculations INSERT references `metric_code IN ('throughput', 'aging', 'ttm')` which must exist from prior migrations.

**Fix:** Add a safety assertion in the migration's `upgrade()` function:
```python
def upgrade():
    # Verify required definitions exist
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT COUNT(*) FROM metrics.definitions WHERE metric_code IN ('throughput', 'aging', 'ttm', 'velocity', 'lead_time', 'cfd', 'backlog_growth', 'flow_efficiency')"
    )).scalar()
    assert result == 8, f"Expected 8 existing definitions, found {result}. Run prior migrations first."

    # ... rest of migration
```

---

### Fix F-017: board_columns format coupling in quality.py

**File:** `pipelines/calculations/quality.py`

**Problem:** `calculate_backflow_rate` expects `status_ids` as array (aggregated) but this is a non-obvious requirement.

**Fix:** Accept individual rows (standard format) and aggregate inside the function:
```python
# In calculate_backflow_rate, at the start:
# If board_columns_df has individual status_id rows (standard format), aggregate them
if "status_id" in board_columns_df.columns and "status_ids" not in board_columns_df.columns:
    board_columns_df = board_columns_df.group_by(["id", "board_id", "name", "position"]).agg(
        pl.col("status_id").alias("status_ids")
    )
```

Update `quality.py` asset to pass board_columns in the standard format (individual rows with `status_id`), and let the calculation handle both.

---

## LOW Fixes

### Fix F-018: Remove unused import in flow_dynamics.py

**File:** `pipelines/calculations/flow_dynamics.py`

Remove `from typing import List` if it's not used. Check other new calculation files for similar unused imports.

---

## After All Fixes: Run These Verifications

```bash
# 1. Run full unit test suite
.venv/Scripts/python.exe -m pytest tests/unit/ -v

# 2. Run ruff linter
.venv/Scripts/python.exe -m ruff check pipelines/calculations/ pipelines/assets/metrics/

# 3. Check imports work
.venv/Scripts/python.exe -c "from pipelines.assets.metrics import *; print('OK')"
.venv/Scripts/python.exe -c "from pipelines.calculations.sprint_health import *; print('OK')"
.venv/Scripts/python.exe -c "from pipelines.calculations.flow_dynamics import *; print('OK')"

# 4. Verify no hardcoded dates remain
grep -rn "20260321\|20260320\|20260319" pipelines/ --include="*.py"
```

## Files to Modify

1. `pipelines/calculations/sprint_health.py` - F-001, F-007, F-013, F-014, F-015
2. `pipelines/calculations/flow_dynamics.py` - F-003, F-018
3. `pipelines/calculations/delivery.py` - F-007, F-009
4. `pipelines/calculations/estimation.py` - F-012
5. `pipelines/calculations/aging.py` - F-011
6. `pipelines/calculations/quality.py` - F-017
7. `pipelines/assets/metrics/sprint_health.py` - F-001, F-002, F-005
8. `pipelines/assets/metrics/flow_dynamics.py` - F-002, F-005
9. `pipelines/assets/metrics/input_flow.py` - F-005
10. `pipelines/assets/metrics/quality.py` - F-005, F-017
11. `pipelines/assets/metrics/delivery.py` - F-005, F-009
12. `pipelines/assets/metrics/cycle_time_ext.py` - F-005
13. `pipelines/assets/metrics/waste.py` - F-005
14. `pipelines/assets/metrics/estimation.py` - F-005, F-006, F-012
15. `pipelines/assets/metrics/aging_extended.py` - F-005, F-011
16. `db/migrations/versions/0026_add_expanded_metrics.py` - F-016
17. `tests/unit/test_sprint_health.py` - F-001, F-015 (fixture fixes)
18. `tests/unit/test_flow_dynamics.py` - F-003 (fixture fixes)
19. `tests/unit/test_estimation.py` - F-012 (column name fix)
