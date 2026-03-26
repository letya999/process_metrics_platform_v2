from contextlib import nullcontext
from unittest.mock import MagicMock, call
from uuid import uuid4

import streamlit_admin.app as admin_app

# --- Mock Helpers ---


def mock_st(monkeypatch):
    """Patch all streamlit calls to avoid side effects and errors."""
    mock = MagicMock()
    # columns returns context-manager-compatible mocks
    mock.columns.side_effect = lambda n: [nullcontext() for _ in range(n)]
    # selectbox must return the first option so dict lookups work
    mock.selectbox.side_effect = (
        lambda label, options, **kwargs: options[0] if options else ""
    )
    # multiselect returns empty list by default
    mock.multiselect.return_value = []
    # checkbox returns False
    mock.checkbox.return_value = False
    # button returns False (no click)
    mock.button.return_value = False
    # expander is a context manager
    mock.expander.return_value = nullcontext()
    monkeypatch.setattr(admin_app, "st", mock)
    return mock


def mock_client():
    """Create a mock client that returns controlled fixture data."""
    return MagicMock()


# --- Tests for _render_settings_json_editor ---


def test_render_flow_status_categories(monkeypatch):
    st = mock_st(monkeypatch)
    # 3 multiselects: active, passive, done
    st.multiselect.side_effect = [
        ["In Progress"],  # active
        ["To Do"],  # passive
        ["Done"],  # done
    ]

    statuses = [
        {"status_id": "s1", "status_name": "To Do"},
        {"status_id": "s2", "status_name": "In Progress"},
        {"status_id": "s3", "status_name": "Done"},
    ]

    result = admin_app._render_settings_json_editor(
        "flow_status_categories", {}, statuses, [], []
    )

    assert result == {
        "active_categories": ["In Progress"],
        "passive_categories": ["To Do"],
        "done_categories": ["Done"],
    }
    assert st.multiselect.call_count == 3


def test_render_issue_type_filter(monkeypatch):
    st = mock_st(monkeypatch)
    st.multiselect.return_value = ["Story", "Bug"]

    issue_types = [
        {"issue_type_id": "it1", "issue_type_name": "Story"},
        {"issue_type_id": "it2", "issue_type_name": "Bug"},
    ]

    result = admin_app._render_settings_json_editor(
        "issue_type_filter", {}, [], issue_types, []
    )
    assert result == {"include": ["Story", "Bug"]}


def test_render_defect_density_types(monkeypatch):
    st = mock_st(monkeypatch)
    st.selectbox.side_effect = ["Bug", "Story"]

    issue_types = [
        {"issue_type_id": "it1", "issue_type_name": "Story"},
        {"issue_type_id": "it2", "issue_type_name": "Bug"},
    ]

    result = admin_app._render_settings_json_editor(
        "defect_density_types", {}, [], issue_types, []
    )
    assert result == {"numerator_type": "Bug", "denominator_type": "Story"}


def test_render_target_status(monkeypatch):
    st = mock_st(monkeypatch)
    # selectbox returns the label; app.py uses status_name
    st.selectbox.return_value = "Done"

    statuses = [{"status_id": "s3", "status_name": "Done"}]

    result = admin_app._render_settings_json_editor(
        "target_status", {}, statuses, [], []
    )
    assert result == {"target_status": "s3"}


def test_render_field_key_id(monkeypatch):
    st = mock_st(monkeypatch)
    # app.py uses f"{f['external_key']} - {f['name']}"
    st.selectbox.return_value = "customfield_101 - Story Points"

    field_keys = [
        {
            "field_key_id": "f1",
            "external_key": "customfield_101",
            "name": "Story Points",
        }
    ]

    result = admin_app._render_settings_json_editor(
        "field_key_id", {}, [], [], field_keys
    )
    assert result == {"field_key_id": "f1"}


def test_render_cancelled_status_ids(monkeypatch):
    st = mock_st(monkeypatch)
    # app.py uses status_name
    st.multiselect.return_value = ["Cancelled", "Rejected"]

    statuses = [
        {"status_id": "s4", "status_name": "Cancelled"},
        {"status_id": "s5", "status_name": "Rejected"},
    ]

    result = admin_app._render_settings_json_editor(
        "cancelled_status_ids", {}, statuses, [], []
    )
    assert result == {"cancelled_status_ids": ["s4", "s5"]}


def test_render_fallback_unknown_type(monkeypatch):
    mock_st(monkeypatch)
    mock_je = MagicMock(return_value={"foo": "bar"})
    monkeypatch.setattr(admin_app, "json_editor", mock_je)

    # "field_value_match" is not explicitly handled with custom UI yet
    result = admin_app._render_settings_json_editor(
        "field_value_match", {"old": "val"}, [], [], []
    )
    assert mock_je.called
    assert result == {"foo": "bar"}


# --- Tests for delete UI in tabs ---


def test_commitment_delete_calls_api(monkeypatch):
    st = mock_st(monkeypatch)
    client = mock_client()
    token = "test-token"

    pid1 = str(uuid4())
    rid1 = str(uuid4())

    projects = [{"project_id": pid1, "project_key": "P1", "project_name": "P1"}]
    contracts = [{"calc_code": "velocity", "requires_commitment": "required"}]
    all_rules = [
        {
            "id": rid1,
            "project_id": pid1,
            "calc_code": "velocity",
            "board_id": "bid1",
            "start_column_name_snapshot": "Todo",
            "end_column_name_snapshot": "Done",
        }
    ]
    boards = [{"board_id": "bid1", "board_name": "Board 1"}]
    columns = [
        {"column_id": "cid1", "column_name": "Todo"},
        {"column_id": "cid2", "column_name": "Done"},
    ]

    client.request.side_effect = [
        projects,  # GET projects
        contracts,  # GET contracts
        all_rules,  # GET rules
        boards,  # GET boards
        columns,  # GET columns
        {"status": "ok"},  # DELETE response
    ]

    # Mock selectbox to pick the rule to delete
    # Label is "P1 | velocity | <rid1>"
    rule_label = f"P1 | velocity | {rid1}"

    def fake_selectbox(label, options, **kwargs):
        if "to delete" in label.lower():
            return rule_label
        return options[0]

    st.selectbox.side_effect = fake_selectbox
    st.button.return_value = True  # Click delete

    admin_app._tab_commitment_v2(client, token)

    # Verify DELETE call
    client.request.assert_has_calls(
        [call("DELETE", f"/admin/commitment-rules/{rid1}", token=token)], any_order=True
    )


def test_settings_delete_calls_api(monkeypatch):
    st = mock_st(monkeypatch)
    client = mock_client()
    token = "test-token"

    sid1 = str(uuid4())
    pid1 = str(uuid4())

    projects = [{"project_id": pid1, "project_key": "P1", "project_name": "P1"}]
    contracts = [
        {"calc_code": "ttm_days", "required_settings_types": ["issue_type_filter"]}
    ]
    all_settings = [
        {
            "id": sid1,
            "project_id": pid1,
            "calc_code": "ttm_days",
            "settings_type": "issue_type_filter",
            "enabled": True,
            "settings_json": {"include": ["Epic"]},
        }
    ]

    client.request.side_effect = [
        projects,  # GET projects
        contracts,  # GET contracts
        all_settings,  # GET settings
        [],  # GET statuses
        [],  # GET issue types
        [],  # GET field keys
        {"status": "ok"},  # DELETE response
    ]

    setting_label = f"P1 | ttm_days | issue_type_filter | {sid1}"

    def fake_selectbox(label, options, **kwargs):
        if "to delete" in label.lower():
            return setting_label
        return options[0]

    st.selectbox.side_effect = fake_selectbox
    st.button.return_value = True

    admin_app._tab_settings_v2(client, token)

    client.request.assert_has_calls(
        [call("DELETE", f"/admin/calculation-settings/{sid1}", token=token)],
        any_order=True,
    )


def test_units_delete_calls_api(monkeypatch):
    st = mock_st(monkeypatch)
    client = mock_client()
    token = "test-token"

    uid1 = str(uuid4())
    pid1 = str(uuid4())

    projects = [{"project_id": pid1, "project_key": "P1", "project_name": "P1"}]
    contracts = [
        {
            "calc_code": "velocity",
            "requires_unit_binding": "required",
            "unit_code": "story_points",
        }
    ]
    all_units = [
        {
            "id": uid1,
            "project_id": pid1,
            "unit_code": "story_points",
            "display_symbol": "SP",
            "source_field_id": "fid1",
        }
    ]
    field_keys = [
        {"field_key_id": "fid1", "external_key": "customfield_101", "name": "SP"}
    ]

    client.request.side_effect = [
        projects,  # GET projects
        contracts,  # GET contracts
        all_units,  # GET units
        field_keys,  # GET fields
        {"status": "ok"},  # DELETE response
    ]

    unit_label = f"P1 | story_points | fid1 | {uid1}"

    def fake_selectbox(label, options, **kwargs):
        if "to delete" in label.lower():
            return unit_label
        return options[0]

    st.selectbox.side_effect = fake_selectbox
    st.button.return_value = True

    admin_app._tab_units_v2(client, token)

    client.request.assert_has_calls(
        [call("DELETE", f"/admin/units/{uid1}", token=token)], any_order=True
    )


def test_slices_delete_calls_api(monkeypatch):
    st = mock_st(monkeypatch)
    client = mock_client()
    token = "test-token"

    srid1 = str(uuid4())

    projects = [{"project_id": "pid1", "project_key": "P1", "project_name": "P1"}]
    contracts = [{"calc_code": "velocity", "supports_slicing": True}]
    all_slices = [
        {
            "id": srid1,
            "project_id": "pid1",
            "rule_name": "By Type",
            "enabled": True,
            "target_definition_id": None,
            "target_definition_name": None,
            "source_table": "clean_jira.issues",
            "group_by_source_column": "issue_type_id",
        }
    ]
    schema_map = {
        "tables": [
            {
                "table_name": "clean_jira.issues",
                "columns": [{"column_name": "issue_type_id"}],
            }
        ],
        "relations": [],
    }

    client.request.side_effect = [
        projects,  # GET projects
        contracts,  # GET contracts
        all_slices,  # GET slices
        schema_map,  # GET schema
        {"status": "ok"},  # DELETE response
    ]

    slice_label = f"P1 | By Type | {srid1}"

    def fake_selectbox(label, options, **kwargs):
        if "to delete" in label.lower():
            return slice_label
        return options[0]

    st.selectbox.side_effect = fake_selectbox
    st.button.return_value = True

    admin_app._tab_slices_v2(client, token)

    client.request.assert_has_calls(
        [call("DELETE", f"/admin/slice-rules/{srid1}", token=token)], any_order=True
    )


# --- Tests for global missing-check fixes ---


def test_commitment_missing_global_covers_all(monkeypatch):
    st = mock_st(monkeypatch)
    client = mock_client()
    token = "test-token"

    # 3 projects, one global rule for velocity
    projects = [
        {"project_id": "p1", "project_key": "P1", "project_name": "Project 1"},
        {"project_id": "p2", "project_key": "P2", "project_name": "Project 2"},
        {"project_id": "p3", "project_key": "P3", "project_name": "Project 3"},
    ]
    contracts = [{"calc_code": "velocity", "requires_commitment": "required"}]
    # project_id=None means Global
    all_rules = [
        {
            "id": "r1",
            "project_id": None,
            "calc_code": "velocity",
            "board_id": "b1",
            "start_column_name_snapshot": "S",
            "end_column_name_snapshot": "E",
        }
    ]

    client.request.side_effect = [
        projects,
        contracts,
        all_rules,
        [],  # boards
        [],  # columns
    ]

    admin_app._tab_commitment_v2(client, token)

    # Global rule covers all projects — success message shown, no missing dataframe
    success_calls = [str(c) for c in st.success.call_args_list]
    assert any(
        "All required commitment rules are configured" in c for c in success_calls
    )


def test_settings_missing_global_covers_all(monkeypatch):
    st = mock_st(monkeypatch)
    client = mock_client()
    token = "test-token"

    projects = [
        {"project_id": "p1", "project_key": "P1", "project_name": "Project 1"},
        {"project_id": "p2", "project_key": "P2", "project_name": "Project 2"},
    ]
    contracts = [
        {"calc_code": "ttm_days", "required_settings_types": ["issue_type_filter"]}
    ]
    all_settings = [
        {
            "id": "s1",
            "project_id": None,
            "calc_code": "ttm_days",
            "settings_type": "issue_type_filter",
            "enabled": True,
            "settings_json": {"include": ["Epic"]},
        }
    ]

    client.request.side_effect = [
        projects,
        contracts,
        all_settings,
        [],  # statuses
        [],  # issue types
        [],  # field keys
    ]

    admin_app._tab_settings_v2(client, token)

    success_calls = [str(c) for c in st.success.call_args_list]
    assert any(
        "All required calculation settings are configured" in c for c in success_calls
    )
