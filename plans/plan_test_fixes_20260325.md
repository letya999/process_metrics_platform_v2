# Plan: Fix failing tests and add new test coverage
Date: 2026-03-25
Context: After ETL audit fixes (session plan_etl_audit_fixes_20260325.md), 29 unit tests fail.
Run tests with: `.venv/Scripts/python.exe -m pytest tests/unit/ -q --tb=short`

---

## Overview of failures (all in test suite, code is correct)

29 tests fail across 3 files:
- `tests/unit/test_jira_clean_assets_unit.py` — 27 failures
- `tests/unit/test_metric_assets_aging_flow.py::test_calculate_flow_efficiency_success` — 1 failure
- `tests/unit/test_metric_asset_sprint_health.py::test_calculate_sprint_health_success` — 1 failure

---

## Fix 1 — Clear `_TABLE_EXISTS_CACHE` between tests (root cause of many failures)

**File:** `tests/conftest.py`

Add an `autouse=True` fixture that clears the module-level `_TABLE_EXISTS_CACHE` dict in `_utils.py` between every test.
Append to the end of `tests/conftest.py`:

```python
@pytest.fixture(autouse=True)
def clear_table_exists_cache():
    """Clear _TABLE_EXISTS_CACHE between tests to prevent cross-test pollution."""
    from pipelines.assets.jira.clean._utils import _TABLE_EXISTS_CACHE
    _TABLE_EXISTS_CACHE.clear()
    yield
    _TABLE_EXISTS_CACHE.clear()
```

---

## Fix 2 — Add `rollback()` to mock connection in test_jira_clean_assets_unit.py

**File:** `tests/unit/test_jira_clean_assets_unit.py`

The `_ExceptionOnFirst` class used in `TestHierarchyLevelMapping` must get a `rollback` method:

Find the class `_ExceptionOnFirst` (around line 1440-1455) and add:
```python
    def rollback(self):
        pass
```

---

## Fix 3 — Update TRUNCATE→DELETE assertions

**File:** `tests/unit/test_jira_clean_assets_unit.py`

Class `TestTruncateBeforeRebuild` has two tests that check for `TRUNCATE`. Since C-3 fix changed TRUNCATE to DELETE (correct behavior), update the assertions:

In `test_truncate_is_first_executed_statement`:
- Change: `assert 'TRUNCATE' in first_sql`
- To: `assert 'DELETE' in first_sql` (or `assert 'DELETE FROM CLEAN_JIRA.SPRINT_ISSUES_CHANGELOG' in first_sql`)
- Update the test docstring/comment to reference C-3 fix

In `test_insert_follows_truncate`:
- Update to check for `DELETE` instead of `TRUNCATE`
- Rename to `test_delete_is_first_executed_statement` and `test_insert_follows_delete`

---

## Fix 4 — Ghost cleanup tests: handle new M-2 pagination safety check

**File:** `tests/unit/test_jira_clean_assets_unit.py`

The M-2 fix added `SELECT COUNT(*) FROM raw_jira.issues` at the start of `jira_ghost_cleanup`.
The mock DB connections in these tests must handle this new query.

Affected tests/classes:
1. `test_jira_ghost_cleanup_success` — mock must return a scalar for `SELECT COUNT(*) FROM raw_jira.issues`
2. `TestGhostCleanupEdgeCases::test_skips_deletion_when_api_returns_empty`
3. `TestGhostCleanupEdgeCases::test_does_not_delete_when_raw_is_subset_of_api`
4. `TestGhostCleanupEdgeCases::test_ghost_cleanup_uses_expanding_in_clause`

Look for where these tests build mock connections (around the class definition for `TestGhostCleanupEdgeCases`). The mock `execute` dispatch needs a branch:
```python
if 'COUNT' in str(statement) and 'raw_jira.issues' in str(statement):
    mock_result = MagicMock()
    mock_result.scalar.return_value = <appropriate_count>
    return mock_result
```

For `test_skips_deletion_when_api_returns_empty`, the API returns 0 issues. The new code first checks `total_raw_issues > 0 and len(all_issue_ids) < total_raw_issues * 0.9`. Since `len(all_issue_ids) == 0`, the condition `0 < 0 * 0.9` is False (0 < 0 is False), so the M-2 guard is skipped. Then the `if not all_issue_ids: return skipped` path triggers. So the mock must:
- Return `0` for the COUNT query (or any value, since with empty all_issue_ids the guard doesn't trigger)
- The test should still expect `status: skipped` as before

For the other tests that have actual issue IDs, return a count equal to the number of IDs in the mock DB.

Also fix `test_jira_ghost_cleanup_success` which fails with `Unexpected SQL execute call: SELECT id::text FROM raw_jira.issues`. The mock must handle this too. Looking at the execution flow:
1. `SELECT COUNT(*) FROM raw_jira.issues` — count query
2. `SELECT id::text FROM raw_jira.issues` — get current IDs

The mock must handle both.

---

## Fix 5 — Fix `issues.py:260 TypeError: NoneType > int`

**File:** `tests/unit/test_jira_clean_assets_unit.py`

The new C-4 code in `issues.py` calls `drop_count_result.scalar()` then does `if drop_count > 0`. The mock connection returns a `MagicMock()` by default for `.scalar()`, which is a `MagicMock` object, not an int.

The test mock for `clean_jira_issues` must return an int from scalar() for the new COUNT queries:
- `SELECT COUNT(*) FROM raw_jira.issues WHERE (it.id IS NULL OR ist.id IS NULL)` — return `0`
- `SELECT COUNT(*) FROM raw_jira.issues WHERE fields__created IS NULL` — return `0`

Find `test_clean_jira_issues_success` and update the mock's `execute` handling to return `0` for these COUNT queries.

---

## Fix 6 — `_table_exists` now used in checks: mock must handle `information_schema.tables`

**File:** `tests/unit/test_jira_clean_assets_unit.py`

`TestJiraDataQuality` tests (test_check_passes_when_counts_match, test_check_passes_within_threshold, test_check_skips_when_no_raw_table) fail because `checks.py` now uses `_table_exists` helper (which queries `information_schema.tables`), but the tests mock the DB directly and the mock `execute` raises `AssertionError` on `SELECT COUNT(*) FROM clean_jira.issues`.

Look at how these tests set up mock DB connections. The mock needs to:
1. Handle `information_schema.tables` query: return `True` (table exists) for `raw_jira.issues`
2. Handle `COUNT(*)` query for raw count
3. Handle `COUNT(*)` query for clean count

Alternatively, since `_table_exists` is now a utility in `_utils.py`, mock it at the module level:
In each test, add `monkeypatch` or patch `_table_exists` to return `True`.

The cleanest fix: For `test_check_skips_when_no_raw_table`, patch `_table_exists` to return `False`.
For the other two tests, patch `_table_exists` to return `True` and then also handle the COUNT queries.

But since `checks.py` does a local import `from ._utils import _table_exists`, patching must be done on the module:
```python
from pipelines.assets.jira.clean import checks as checks_mod
from pipelines.assets.jira.clean._utils import _TABLE_EXISTS_CACHE
# or monkeypatch:
monkeypatch.setattr('pipelines.assets.jira.clean.checks._table_exists', lambda *a: True)
```

---

## Fix 7 — `TestDetectSprintFieldId::test_logs_warning_on_exception_fallback`

**File:** `tests/unit/test_jira_clean_assets_unit.py`

The log message changed from `"falling back to customfield_10020"` to `"falling back to candidate list"`.

Find this test (around line 860) and update the assertion:
- Old: `assert 'customfield_10020' in caplog.text`
- New: `assert 'candidate list' in caplog.text` or `assert 'falling back' in caplog.text`

---

## Fix 8 — `test_clean_jira_labels_success` (assert 0 == 3 at line 187)

**File:** `tests/unit/test_jira_clean_assets_unit.py`

The `clean_jira_labels` asset now uses `_table_exists` helper (which queries `information_schema.tables`). If the mock connection doesn't handle this query, `_table_exists` returns False, and the label insert is skipped (returns `{"status": "skipped"}`). The test then checks insert count and gets 0.

Fix: In the mock connection for this test, handle `information_schema.tables` query to return `True` (table exists). Since `_TABLE_EXISTS_CACHE` is now cleared between tests (Fix 1), each test starts fresh.

The mock `execute` needs to detect `information_schema.tables` queries and return an appropriate value (True/exists scalar).

---

## Fix 9 — `test_clean_jira_field_keys_success` (assert 0 == 2 at line 262)

**File:** `tests/unit/test_jira_clean_assets_unit.py`

The field_keys asset now queries `SELECT id FROM clean_jira.projects`. The mock must return project IDs for this new query. Without it, `project_ids` is empty and no field keys are inserted.

Find the mock for `test_clean_jira_field_keys_success` and add handling for:
- `SELECT id FROM clean_jira.projects` — return rows with project IDs

Also check `TestFieldKeyFiltering::test_field_keys_count_in_asset` — same issue.

---

## Fix 10 — `test_clean_jira_field_values_success` AttributeError `execution_options`

**File:** `tests/unit/test_jira_clean_assets_unit.py` or `pipelines/assets/jira/clean/supplementary.py`

`supplementary.py:341` calls `conn.execution_options(...)` during batch insert refactor. The test's `_SequencedConnection` mock doesn't have `execution_options`.

Two options:
1. Add `execution_options = lambda *a, **kw: self` to `_SequencedConnection`
2. Check the actual supplementary.py line 341 and fix how `execution_options` is called

Since `_SequencedConnection` is a custom test mock, add the method to it.

---

## Fix 11 — Tests that check return value keys that changed

**File:** `tests/unit/test_jira_clean_assets_unit.py`

`KeyError: 'sprint_issues_count'` — `test_clean_jira_sprint_assets_success` expects a return dict with `sprint_issues_count` key. Check what `clean_jira_sprint_issues` now returns and update the assertion to match.

`KeyError: 'releases_count'` — `test_clean_jira_release_assets_skip_and_success` expects `releases_count`. Update assertion.

`KeyError: 'changelog_entries'` — `test_clean_jira_misc_assets_success` expects `changelog_entries`. Update assertion.

For all three: read the actual return values from the asset code and update the test assertions accordingly.

---

## Fix 12 — `TestLossPercentageBoundary` failures (assert -9900.0 == 0.0 etc)

**File:** `tests/unit/test_jira_clean_assets_unit.py`

These tests call `check_raw_clean_issue_count` which now uses `_table_exists` internally. The mock connection is giving unexpected values (the `-9900.0` suggests a MagicMock is being used as a number).

The check is: `(raw_count - clean_count) / raw_count * 100 > 5.0`. If `raw_count` and `clean_count` are MagicMock objects, arithmetic gives weird results.

Fix: Ensure the mock returns proper integers for COUNT queries. The mock must handle:
1. `information_schema.tables` query (from `_table_exists`) → return True
2. `COUNT(*) FROM raw_jira.issues` → return expected int
3. `COUNT(*) FROM clean_jira.issues` → return expected int

Find how the test sets up these mocks and ensure scalar() returns ints.

Also: `assert True is False` for `test_zero_clean_is_100_percent_loss` and `test_above_5_percent_loss_fails` — same root cause.

---

## Fix 13 — `test_calculate_flow_efficiency_success` in test_metric_assets_aging_flow.py

**File:** `tests/unit/test_metric_assets_aging_flow.py`

The `_read_table` mock (around line 203) raises `AssertionError` for unknown queries. The new C-1 code queries `calculation_settings`:
```sql
SELECT project_id, settings_json FROM metrics.calculation_settings
WHERE target_calculation_id = :def_id AND settings_type = 'flow_status_categories' AND enabled = true
```

Also, `issue_statuses` query now requests `id, project_id, name, category` (added `project_id`).

In `_read_table`, add a branch:
```python
if 'calculation_settings' in query and 'flow_status_categories' in query:
    # Return project-specific settings for test project P1
    return pl.DataFrame({
        "project_id": ["P1"],
        "settings_json": [{"active_categories": ["in_progress"], "passive_categories": ["to_do"], "done_categories": ["done"]}],
    })
```

Also add `project_id` column to the `issue_statuses` mock return:
```python
if 'issue_statuses' in query:
    return pl.DataFrame({
        "id": ["s1", "s2", "s3"],
        "project_id": ["P1", "P1", "P1"],
        "name": ["To Do", "In Progress", "Done"],
        "category": ["to_do", "in_progress", "done"],
    })
```

The test also currently uses `active_statuses`/`wait_statuses`/`end_statuses` variables that no longer exist. Look for these in the test and remove them — the logic is now driven by `calculation_settings`.

---

## Fix 14 — `test_calculate_sprint_health_success` in test_metric_asset_sprint_health.py

**File:** `tests/unit/test_metric_asset_sprint_health.py`

`resolve_unit_field(engine, p_id, "story_points")` is now called in `sprint_health.py`. The test passes `object()` as engine, which doesn't have `.connect()`.

Add monkeypatch for `resolve_unit_field`:
```python
monkeypatch.setattr(
    sprint_health, "resolve_unit_field",
    lambda engine, project_id, unit_code: {"source_field_id": "customfield_10016"}
)
```

The `field_keys_df` mock (returned by `read_table` for the field_keys query) must include a row with `external_key = "customfield_10016"` so `sp_field_key_map` gets populated.

Also check: the `_read_table` function in this test — add handling for the field_keys query if needed.

---

## New tests to write

### New file: `tests/unit/test_flow_efficiency_asset.py`

Write tests for `calculate_flow_efficiency` asset (the Dagster asset function in `pipelines/assets/metrics/flow_efficiency.py`):

1. `test_flow_efficiency_skips_project_without_settings` — project has no entry in `calculation_settings`; asset should skip it with a warning log
2. `test_flow_efficiency_uses_settings_per_project` — two projects, each has different `active_categories` in `calculation_settings`; verify each project uses its own status IDs
3. `test_flow_efficiency_skips_all_when_no_settings` — no calculation_settings entries; asset returns `{"status": "no_data"}`
4. `test_flow_efficiency_slice_calc_uses_project_status_maps` — verify `flow_slice_calc` closure uses `project_status_maps` correctly for multi-project subsets

Use the `monkeypatch` pattern from `test_metric_assets_aging_flow.py` as reference.

### New tests in: `tests/unit/test_metric_asset_sprint_health.py`

Add test: `test_sprint_health_uses_resolve_unit_field_per_project`
- Verify that `resolve_unit_field` is called per project_id with `"story_points"` code
- Mock `resolve_unit_field` to return different field IDs per project
- Assert that `sp_field_key_map` uses those IDs

### New tests in: `tests/unit/test_jira_clean_assets_unit.py`

Add test class `TestDeleteBeforeRebuild` (replaces the truncate tests):
1. `test_delete_is_first_executed_statement` — verify `DELETE FROM clean_jira.sprint_issues_changelog` is the first SQL
2. `test_insert_follows_delete` — verify INSERT follows DELETE

Add test: `test_ghost_cleanup_aborts_when_api_returns_partial_list`
- API returns only 10% of DB issues (simulates partial pagination)
- Expected: `{"status": "aborted_incomplete_api_response"}`
- Mock: `COUNT(*) FROM raw_jira.issues` returns 1000; API returns 50 IDs

Add test: `test_flow_efficiency_nonzero_check`
- Create mock for `check_flow_efficiency_nonzero` asset check
- All-zero values → check fails
- Some nonzero values → check passes
- No data → check passes with status "no_data"

---

## Execution order

1. Run tests first to confirm count: `.venv/Scripts/python.exe -m pytest tests/unit/ -q 2>&1 | tail -5`
2. Apply all fixes to test files (do NOT change production code)
3. Run tests again to confirm all 29 failures are resolved
4. Write new tests
5. Run full test suite one more time: `.venv/Scripts/python.exe -m pytest tests/unit/ -q 2>&1 | tail -5`

All tests should pass. If a test was testing wrong behavior (TRUNCATE), update it to test the correct behavior (DELETE). Do NOT revert production code to make tests pass — fix the tests to match the new correct behavior.

---

## Key technical details

- `_TABLE_EXISTS_CACHE` is in `pipelines/assets/jira/clean/_utils.py` as a module-level dict
- `_table_exists(conn, schema, table)` — first arg is SQLAlchemy connection
- `resolve_unit_field(engine, project_id, unit_code)` is in `pipelines/utils/metric_registry.py`
- `calculation_settings` table: `(id, project_id nullable, target_calculation_id, settings_type TEXT, settings_json JSONB, enabled BOOL)`
- Flow efficiency settings_type: `'flow_status_categories'`
- settings_json format: `{"active_categories": ["in_progress"], "passive_categories": ["to_do"], "done_categories": ["done"]}`
- Test runner: `.venv/Scripts/python.exe -m pytest tests/unit/ -q --tb=short`
