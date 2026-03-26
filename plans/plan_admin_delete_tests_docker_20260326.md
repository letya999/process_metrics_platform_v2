# Admin Delete UI Tests + Docker Rebuild — 2026-03-26

## Context

The previous session implemented:
- Delete buttons in all four admin tabs (Commitment, Calc Settings, Units, Slices)
- New `DELETE /admin/units/{unit_id}` FastAPI endpoint
- `_render_settings_json_editor()` helper with structured UI per settings_type
- Global (NULL project_id) missing-check fixes across all tabs

This plan adds missing test coverage for those new features, then rebuilds the
`app` and `admin-ui` Docker images.

---

## Part 1: Missing tests to add

### File: `tests/unit/test_api_admin_unit.py`

Add `test_delete_unit_success_and_404` after the existing
`test_units_list_upsert_and_conflict` test:

```python
@pytest.mark.asyncio
async def test_delete_unit_success_and_404():
    db = _make_db()
    admin = AdminSession(str(uuid4()), "a@x", "A", True, datetime.now(UTC) + timedelta(hours=1))
    uid = uuid4()

    mock_ok = MagicMock()
    mock_ok.rowcount = 1
    mock_404 = MagicMock()
    mock_404.rowcount = 0

    db.execute = AsyncMock(side_effect=[mock_ok, mock_404])

    result = await admin_api.delete_unit(uid, db, admin)
    assert result["status"] == "ok"

    with pytest.raises(HTTPException) as exc:
        await admin_api.delete_unit(uuid4(), db, admin)
    assert exc.value.status_code == 404
```

### File: `tests/unit/test_tab_delete_ui.py` (NEW)

Create this new test file covering delete UI for all four tabs and the
`_render_settings_json_editor` helper.

#### Imports and helpers

```python
from contextlib import nullcontext
from unittest.mock import MagicMock, call
import pytest
import streamlit_admin.app as admin_app
```

Standard mock helpers: patch all st.* UI calls, make client.request return
sensible minimal fixture data for each tab.

#### Tests for `_render_settings_json_editor`

Test each settings_type branch returns correct dict structure:

1. `test_render_flow_status_categories` — provide statuses with categories
   ["In Progress", "To Do", "Done"], mock 3 multiselects returning those lists,
   assert result == `{"active_categories": [...], "passive_categories": [...],
   "done_categories": [...]}`.

2. `test_render_issue_type_filter` — provide issue_types list, mock multiselect,
   assert result == `{"include": [...]}`.

3. `test_render_defect_density_types` — mock 2 selectboxes (num/den), assert
   result == `{"numerator_type": "Bug", "denominator_type": "Story"}`.

4. `test_render_target_status` — provide statuses, mock selectbox, assert
   result == `{"target_status": "<status_id>"}`.

5. `test_render_field_key_id` — provide field_keys, mock selectbox, assert
   result == `{"field_key_id": "<field_key_id>"}`.

6. `test_render_cancelled_status_ids` — provide statuses, mock multiselect
   returning 2 names, assert result == `{"cancelled_status_ids": [id1, id2]}`.

7. `test_render_fallback_unknown_type` — pass settings_type="field_value_match",
   mock json_editor, assert json_editor was called once.

#### Tests for delete UI in tabs

For each tab, the test pattern is:
- Set up client.request side effects with minimal fixture data
- Mock all required st.* calls
- Mock `st.selectbox` to return a specific "selected item" label
- Mock `st.button` to return True (simulating delete click)
- Assert that `client.request` was called with DELETE and the correct URL

8. `test_commitment_delete_calls_api` — mock all the data loading calls
   (projects, contracts, commitment-rules), mock selectbox to pick a rule id,
   mock button=True, assert `client.request("DELETE", "/admin/commitment-rules/<id>")` called.

9. `test_settings_delete_calls_api` — same for settings tab:
   mock selectbox to pick a setting, button=True, assert DELETE call.

10. `test_units_delete_calls_api` — mock units data, selectbox picks a unit,
    button=True, assert `client.request("DELETE", "/admin/units/<id>")` called.

11. `test_slices_delete_calls_api` — mock slices data, selectbox picks a rule,
    button=True, assert DELETE call.

#### Tests for global missing-check fixes

12. `test_commitment_missing_global_covers_all` — all_rules has one entry with
    project_id=None for calc_code "velocity". Projects list has 3 projects. After
    running the missing logic inside `_tab_commitment_v2`, assert that
    `st.success` is called (not `st.dataframe` with missing rows).

13. `test_settings_missing_global_covers_all` — similar for calc settings tab:
    all_settings has one global (project_id=None) enabled entry for
    calc_code="ttm_days", settings_type="issue_type_filter". Projects: 2 projects.
    req_by_calc: {"ttm_days": ["issue_type_filter"]}. Assert st.success called
    for the missing expander.

---

## Implementation notes

### How to mock _tab_commitment_v2 delete section

`_tab_commitment_v2` accesses `project_key_by_id` before the delete section.
The simplest approach is to fully mock the tab function by stubbing at the level
of calling `_tab_commitment_v2` with monkeypatched st.* calls and verifying
`client.request` call args.

The key pattern for testing delete:

```python
# st.selectbox returns label; we need a label that maps to a known ID in del_options
# The tab builds del_options like: "Global | velocity | <id>" -> id
# So we need to control which label selectbox returns

call_count = 0
def fake_selectbox(label, options, **kwargs):
    nonlocal call_count
    call_count += 1
    # Return the second option (first real rule label) for the delete selectbox
    if "delete" in label.lower() or "to delete" in options[0]:
        return options[1]  # first real rule (not "-- select --")
    return options[0]

monkeypatch.setattr(admin_app.st, "selectbox", fake_selectbox)
monkeypatch.setattr(admin_app.st, "button", lambda *args, **kwargs: True)
```

### Minimal fixture data requirements per tab

**commitment**:
```python
projects = [{"project_id": "pid1", "project_key": "P1", "project_name": "P1"}]
contracts = [{"calc_code": "velocity", "requires_commitment": "required", ...}]
all_rules = [{"id": "rid1", "project_id": "pid1", "calc_code": "velocity",
              "board_id": "bid1", "start_column_name_snapshot": "Todo",
              "end_column_name_snapshot": "Done"}]
boards = [{"board_id": "bid1", "board_name": "Board 1"}]
board_columns = [{"column_id": "cid1", "column_name": "Todo"},
                 {"column_id": "cid2", "column_name": "Done"}]
```

client.request side_effect order for `_tab_commitment_v2`:
1. GET /admin/catalog/projects → projects
2. GET /admin/contracts/catalog → contracts
3. GET /admin/commitment-rules → all_rules
4. GET /admin/catalog/boards → boards
5. GET /admin/catalog/board-columns → columns
6. DELETE /admin/commitment-rules/rid1 → {"status": "ok"}  (if button=True)

**settings**:
```python
projects = [{"project_id": "pid1", "project_key": "P1", "project_name": "P1"}]
contracts = [{"calc_code": "ttm_days", "required_settings_types": ["issue_type_filter"], ...}]
all_settings = [{"id": "sid1", "project_id": "pid1", "calc_code": "ttm_days",
                 "settings_type": "issue_type_filter", "enabled": True,
                 "settings_json": {"include": ["Epic"]}}]
# + catalog calls for statuses, issue types, field keys
```

**units**:
```python
projects = [{"project_id": "pid1", "project_key": "P1", "project_name": "P1"}]
contracts = [{"calc_code": "velocity", "requires_unit_binding": "required",
              "unit_code": "story_points", ...}]
all_units = [{"id": "uid1", "project_id": "pid1", "unit_code": "story_points",
              "display_symbol": "SP", "source_field_id": "fid1"}]
field_keys = [{"field_key_id": "fid1", "external_key": "customfield_10016",
               "name": "Story Points"}]
```

**slices**:
```python
projects = [{"project_id": "pid1", "project_key": "P1", "project_name": "P1"}]
contracts = [{"calc_code": "velocity", "supports_slicing": True, ...}]
all_slices = [{"id": "srid1", "project_id": "pid1", "rule_name": "By Type",
               "enabled": True, "target_definition_id": None,
               "target_definition_name": None,
               "source_table": "clean_jira.issues",
               "group_by_source_column": "issue_type_id"}]
schema_map = {"tables": [{"table_name": "clean_jira.issues",
                           "columns": [{"column_name": "issue_type_id"}]}],
              "relations": []}
```

---

## Part 2: Docker rebuild

After tests pass, rebuild only `app` and `admin-ui` containers (Dagster and
Metabase are unchanged):

```bash
docker compose -f docker-compose.simple.yml build app admin-ui
```

Do NOT restart running containers — only build images. The user will deploy
when ready.

---

## Files to modify/create

1. `tests/unit/test_api_admin_unit.py` — add `test_delete_unit_success_and_404`
2. `tests/unit/test_tab_delete_ui.py` (NEW) — all delete UI tests + render tests
3. Docker rebuild command (bash, not file edit)

## Order of operations

1. Add `test_delete_unit_success_and_404` to `test_api_admin_unit.py`
2. Create `tests/unit/test_tab_delete_ui.py` with all 13 tests
3. Run `python -m pytest tests/unit/test_api_admin_unit.py tests/unit/test_tab_delete_ui.py -x -q` to verify
4. Run full unit suite: `python -m pytest tests/unit/ -x -q` to confirm no regressions
5. Run `docker compose -f docker-compose.simple.yml build app admin-ui`
