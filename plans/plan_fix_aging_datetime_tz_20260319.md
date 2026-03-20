# Plan: Fix aging.py datetime timezone supertype error

## Bug

`tests/unit/test_aging.py::test_calculate_work_item_aging_facts_without_changelog_sets_zero_status_age`

**Error**: `polars.exceptions.ComputeError: failed to determine supertype of datetime[μs] and datetime[μs, UTC]`

**Root cause**: `pipelines/calculations/aging.py:85`

```python
active_issues = active_issues.with_columns(
    pl.lit(None).cast(pl.Datetime).alias("start_at_from_changelog")
)
```

`pl.Datetime` (no timezone) is created when `status_changelog_df` is empty. Then `pl.coalesce([pl.col("start_at_from_changelog"), pl.col("jira_created_at")])` on line 94-96 fails because `jira_created_at` is `datetime[μs, UTC]` and `start_at_from_changelog` is `datetime[μs]` — Polars cannot determine a supertype between timezone-aware and timezone-naive datetime.

## Fix

**File**: `pipelines/calculations/aging.py`, line 85

Change:
```python
pl.lit(None).cast(pl.Datetime).alias("start_at_from_changelog")
```

To:
```python
pl.lit(None).cast(pl.Datetime("us", "UTC")).alias("start_at_from_changelog")
```

This ensures that when the fallback null column is created it has the same type `datetime[μs, UTC]` as `jira_created_at`, making `pl.coalesce` work correctly.

## Verification

Run after fix:
```
.venv/Scripts/python.exe -m pytest tests/unit/test_aging.py -v
```

All 4 aging tests must pass. Then run the full unit suite:
```
.venv/Scripts/python.exe -m pytest tests/unit/ -v
```

Expected: 225/225 passed.
