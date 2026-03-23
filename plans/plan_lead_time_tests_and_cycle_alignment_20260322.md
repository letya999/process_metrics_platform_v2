# Plan: Lead Time Tests Hardening + Cycle Time / TTM Alignment

**Date:** 2026-03-22
**Branch:** metrics-expansion-and-calculation-unification

---

## Context

After fixing three bugs in `pipelines/calculations/lead_time.py` (removed `jira_created_at` fallback for
`commitment_start`, added CEIL rounding, fixed pre-reset bug), two existing tests now test OLD removed behavior
and must be replaced. Additionally, `cycle_time_ext.py` and `time_to_market.py` use fractional days (no CEIL)
and lack some of the same correctness logic as lead_time.

---

## Part 1: Fix `tests/unit/test_lead_time_logic.py`

### 1A. Remove/rewrite broken tests (OLD behavior)

**`test_issue_without_start_event_uses_created_at`** (lines 202-233)
- OLD behavior: fallback to `jira_created_at` when no In Progress transition existed
- NEW behavior: issue is EXCLUDED (INNER JOIN, no fallback)
- **Action:** Replace this test with `test_issue_without_commitment_zone_transition_is_excluded`
  - Setup: issue with only `To Do → Done` in changelog (no middle status transition)
  - Assert: `result.is_empty()` - the issue is NOT in the output

**`test_issue_returning_to_done_uses_last_left_end_logic`** (lines 339-385)
- OLD behavior: expected `lead_time_days = 14.0` (Jan 1 → Jan 15, ignoring reset)
- NEW behavior: commitment_start = Jan 8 (after last Done exit, because the Jan 8 transition IS
  `to_status_id = STATUS-IN-PROGRESS` which is >= `last_left_done_at = Jan 8`)
  `commitment_end = Jan 15`, `ceil((Jan15-Jan8).seconds/86400) = 7.0`
- **Action:** Update expected value from `14.0` to `7.0` and update the test docstring to explain
  the pre-reset behavior correctly

### 1B. Add new tests covering current correct behavior

**`test_issue_entering_zone_at_middle_status_not_in_progress`**
- Scenario: `To Do → Testing → Done` (Testing IS in `middle_status_ids`, In Progress is NOT in changelog)
- Expected: issue IS included, `commitment_start_at = Testing entry time`
- Setup: `middle_status_ids = ["STATUS-IN-PROGRESS", "STATUS-TESTING"]`, `end_status_ids = ["STATUS-DONE"]`
- Changelog: `to_status_id=STATUS-TESTING on Jan 3`, `to_status_id=STATUS-DONE on Jan 8`
- Assert: `len(result) == 1`, `commitment_start_at == datetime(2024, 1, 3)`, `lead_time_days == 5.0`

**`test_lead_time_ceil_fractional_hours`**
- Scenario: issue completed in 5 hours (fraction of a day)
- Expected: `lead_time_days = 1.0` (ceil(5/24) = 1)
- Setup: `changed_at_start = Jan 1 08:00`, `changed_at_done = Jan 1 13:00` (5 hours)
- Assert: `result["lead_time_days"][0] == 1.0`

**`test_lead_time_ceil_25_hours`**
- Scenario: 25 hours elapsed
- Expected: `lead_time_days = 2.0` (ceil(25/24) = 2)

**`test_lead_time_ceil_exactly_24_hours`**
- Scenario: exactly 24 hours (1 full day)
- Expected: `lead_time_days = 1.0` (ceil(1.0) = 1)

**`test_pre_reset_commitment_start_after_last_done_exit`**
- Scenario: `In Progress (Jan 1) → Done (Jan 5) → In Progress (Jan 8) → Done (Jan 15)`
  This is the SAME scenario as `test_issue_returning_to_done_uses_last_left_end_logic` but with clear
  explanation that Jan 1 start is IGNORED because it's before `last_left_done_at = Jan 8`
- Expected: `commitment_start_at = Jan 8`, `lead_time_days = 7.0`
- This is the renamed/clarified version of the old test

**`test_issue_with_no_end_status_and_no_resolved_at_is_excluded`**
- Scenario: issue has In Progress transition but no Done transition AND `jira_resolved_at = None`
- Expected: `result.is_empty()` (no commitment_end means excluded)

**`test_multiple_issues_mix_included_and_excluded`**
- Scenario: 3 issues in one call:
  - Issue A: To Do → In Progress → Done (included)
  - Issue B: To Do → Done only (excluded - no commitment zone)
  - Issue C: To Do → Testing → Done (included, Testing is in middle_status_ids)
- Expected: `len(result) == 2`, only A and C in result

---

## Part 2: Align `pipelines/calculations/cycle_time_ext.py`

### 2A. Add CEIL to `calculate_cycle_time_custom`

Current code returns fractional `cycle_days`. For consistency with lead_time behavior, add `.ceil()`.

In function `calculate_cycle_time_custom`, in the final `with_columns`:
```python
# BEFORE:
(
    (pl.col("end_at") - pl.col("start_at")).dt.total_seconds() / (24 * 3600)
).alias("cycle_days")

# AFTER:
(
    (pl.col("end_at") - pl.col("start_at")).dt.total_seconds() / (24 * 3600)
).ceil().alias("cycle_days")
```

### 2B. Add CEIL to `calculate_issue_lifetime`

Same change in function `calculate_issue_lifetime`:
```python
# BEFORE:
(
    (pl.col("done_date") - pl.col("created_at")).dt.total_seconds()
    / (24 * 3600)
).alias("lifetime_days")

# AFTER:
(
    (pl.col("done_date") - pl.col("created_at")).dt.total_seconds()
    / (24 * 3600)
).ceil().alias("lifetime_days")
```

### 2C. Add CEIL to `calculate_epic_delivery_time`

Same change in function `calculate_epic_delivery_time`:
```python
# BEFORE:
(
    (pl.col("epic_end") - pl.col("epic_start")).dt.total_seconds() / (24 * 3600)
).alias("delivery_days")

# AFTER:
(
    (pl.col("epic_end") - pl.col("epic_start")).dt.total_seconds() / (24 * 3600)
).ceil().alias("delivery_days")
```

### 2D. Note: `time_to_market.py` - intentionally NO CEIL

TTM (`time_to_market.py`) measures from `jira_created_at` to release. This is a DIFFERENT metric:
- Not a commitment zone metric (starts from idea creation, not from first commitment)
- Fractional days are acceptable for TTM (it's a long-horizon metric, precision matters less)
- DO NOT add CEIL to time_to_market.py

---

## Part 3: Update `tests/unit/test_cycle_time_ext.py`

### 3A. Update existing tests to match CEIL behavior

**`test_calculate_issue_lifetime_basic`**: was `lifetime_days == 4.0` (Jan 1 → Jan 5 = 4 full days)
- 4 full days ceil(4.0) = 4.0 → no change needed

**`test_calculate_cycle_time_custom_basic`**: was `cycle_days == 2.0` (Jan 1 → Jan 3 = 2 full days)
- 2 full days ceil(2.0) = 2.0 → no change needed

**`test_calculate_epic_delivery_time_basic`**: was `delivery_days == 4.0` (Jan 1 → Jan 5 = 4 full days)
- 4 full days ceil(4.0) = 4.0 → no change needed

These existing tests happen to use exact whole-day durations, so CEIL doesn't change them. Good.

### 3B. Add CEIL-specific tests to `test_cycle_time_ext.py`

**`test_calculate_cycle_time_ceil_fractional`**
- Scenario: start Jan 1 08:00, end Jan 1 20:00 (12 hours = 0.5 days)
- Expected with CEIL: `cycle_days == 1.0` (not 0.5)

**`test_calculate_issue_lifetime_ceil_fractional`**
- Scenario: created Jan 1 08:00, done Jan 1 20:00 (12 hours)
- Expected with CEIL: `lifetime_days == 1.0`

---

## Files to Modify

1. `tests/unit/test_lead_time_logic.py` - fix 2 tests, add 7 new tests
2. `pipelines/calculations/cycle_time_ext.py` - add `.ceil()` to 3 functions
3. `tests/unit/test_cycle_time_ext.py` - add 2 CEIL tests

## Files NOT to Modify

- `pipelines/calculations/lead_time.py` - already correct, do not touch
- `pipelines/calculations/time_to_market.py` - intentionally fractional, do not touch
- `tests/unit/test_time_to_market.py` - no changes needed

---

## Verification

After implementation, run:
```bash
python -m pytest tests/unit/test_lead_time_logic.py tests/unit/test_cycle_time_ext.py -v
```

All tests must pass (green). No skips allowed.
