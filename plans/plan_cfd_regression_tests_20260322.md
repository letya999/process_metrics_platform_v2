# Plan: CFD Regression Tests for Three Fixed Bugs

## Context

Three bugs were fixed in the CFD calculation (commit e69dc35). None are covered by existing tests.
This plan adds targeted regression tests to prevent regressions.

## Files to Modify

### 1. `tests/unit/test_cumulative_flow.py`

Add three new test methods to the existing `TestCumulativeFlow` class:

#### Test A: `test_incremental_done_excludes_pre_window_issues`

Verifies that issues which first reached a "done" status BEFORE the CFD window start
are NOT counted in the Done column at all.

Setup:
- 2 issues: ISS-1 completed 90 days ago (pre-window), ISS-2 completed 3 days ago (in-window)
- Both are currently in "Done" status
- `done_status_ids` contains "DONE" status
- Use `days_back=14`

Assert:
- Done column counts on all dates = 1 (only ISS-2), never 2
- ISS-1 does not appear in Done counts on any date

#### Test B: `test_incremental_done_includes_within_window_issues`

Verifies that issues that first reached Done WITHIN the window start at 0 and grow correctly.

Setup:
- 1 issue transitions to Done on day 5 of a 10-day window
- Use `days_back=10`

Assert:
- Done count = 0 on days 1-4
- Done count = 1 on days 5-10

#### Test C: `test_two_statuses_same_column_aggregate_to_one_row`

Verifies that two statuses mapped to the same board column produce ONE row per date,
not two separate rows with the same column_id.

Setup:
- 2 issues: ISS-1 in "Done" (status S_DONE), ISS-2 in "Canceled" (status S_CANCELED)
- board_columns: both S_DONE and S_CANCELED map to column C_DONE (position 3)
- Both statuses have category "done"
- Use `days_back=3`

Assert:
- For each date, there is exactly ONE row where column_id == "C_DONE"
- `issue_count` for that row = 2 (sum of both statuses)
- No duplicate column_id values per (project_id, date)

### 2. `tests/unit/test_jira_clean.py`

Add a new test class `TestHistoricalStatusSync`:

#### Test D: `test_status_category_inference_from_name`

Tests the name-based fallback category logic used in the changelog INSERT:
- "done", "closed", "canceled", "cancelled", "Выполнено" → "done"
- "to do", "к выполнению", "open", "backlog", "Открыт" → "to_do"
- "in progress", "in review", "on review", "testing", "review" → "in_progress"
- unknown names → "in_progress" (default)

This mirrors the CASE WHEN LOWER(hi.to_string) IN (...) logic in the SQL.

#### Test E: `test_status_present_in_changelog_but_not_current_issues`

Validates the logic for detecting "phantom" statuses (exist in changelog but not in current issues).

Setup (pure Python, no DB):
- current_statuses = {"To Do", "In Progress", "Done"}  (what ETL used to sync)
- changelog_statuses = {"To Do", "In Progress", "Done", "On review"}  (from raw history)

Assert:
- Set difference = {"On review"}
- This status would have been lost without the second INSERT pass
- The deduplication check: if a status name already exists (even with different external_id), it must NOT be inserted again (ON CONFLICT DO NOTHING)

## Implementation Notes

- All tests in `test_cumulative_flow.py` must use fixed dates (not `datetime.now()`) to avoid flakiness.
  Since `calculate_cumulative_flow_diagram` uses `datetime.now()` internally, use `monkeypatch` to
  freeze time or use `days_back` large enough that test data falls within the window.
  Alternative: construct `status_changelog_df` with `changed_at` dates relative to "today - N days"
  using `datetime.now() - timedelta(days=N)` in test setup so they always fall within the window.

- Test C must verify `result.filter(pl.col("column_id") == "C_DONE").group_by(["project_id", "date"]).agg(pl.len()).filter(pl.col("len") > 1).is_empty()` is True.

- Tests D and E are pure logic tests with no external dependencies.

## Acceptance Criteria

- All new tests pass with `pytest tests/unit/test_cumulative_flow.py tests/unit/test_jira_clean.py -v`
- No existing tests broken
- Each test name clearly states which bug scenario it guards against
