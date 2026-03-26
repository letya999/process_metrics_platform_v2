from unittest.mock import MagicMock

import pytest
import streamlit as st

import streamlit_admin.app as admin_app


class SessionState(dict):
    def __getattr__(self, name):
        return self.get(name)

    def __setattr__(self, name, value):
        self[name] = value


@pytest.fixture
def fake_state(monkeypatch):
    state = SessionState()
    monkeypatch.setattr(st, "session_state", state)
    return state


def mock_streamlit_common(monkeypatch):
    monkeypatch.setattr(admin_app, "section_title", MagicMock())
    monkeypatch.setattr(admin_app, "_project_filter", MagicMock(return_value=None))
    monkeypatch.setattr(admin_app, "_calc_filter", MagicMock(return_value=None))

    # Handle both int and list for columns
    def smart_columns(spec):
        if isinstance(spec, int):
            return [MagicMock() for _ in range(spec)]
        return [MagicMock() for _ in range(len(spec))]

    monkeypatch.setattr(st, "columns", MagicMock(side_effect=smart_columns))

    monkeypatch.setattr(
        st,
        "expander",
        MagicMock(return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock())),
    )
    monkeypatch.setattr(st, "markdown", MagicMock())
    monkeypatch.setattr(st, "caption", MagicMock())
    monkeypatch.setattr(st, "success", MagicMock())
    monkeypatch.setattr(admin_app, "save_bar", MagicMock(return_value=False))

    # Generic selectbox mock that handles common cases
    def mock_selectbox(label, options, **kwargs):
        if label == "Project":
            return options[0]  # Default to first
        if label == "Field Source Project":
            # Must return one of the project keys, not "All (NULL)"
            return [o for o in options if o != "All (NULL)"][0]
        return options[0]

    monkeypatch.setattr(st, "selectbox", mock_selectbox)


def test_units_missing_global_binding_not_shown_as_missing(monkeypatch, fake_state):
    """BUG-1: Global (NULL project_id) unit binding with source_field_id should satisfy requirement."""
    client = MagicMock()
    client.request.side_effect = [
        [
            {"project_id": "p1", "project_key": "P1", "project_name": "Project 1"}
        ],  # projects
        [
            {"calc_code": "c1", "unit_code": "u1", "requires_unit_binding": "required"}
        ],  # contracts
        [
            {"project_id": None, "unit_code": "u1", "source_field_id": "f1"}
        ],  # all_units (GLOBAL)
        [],  # field-keys (called during render)
    ]

    mock_streamlit_common(monkeypatch)

    captured_dfs = []

    def mock_dataframe(data, **kwargs):
        captured_dfs.append(data)

    monkeypatch.setattr(st, "dataframe", mock_dataframe)

    success_called = False

    def mock_success(msg):
        nonlocal success_called
        success_called = True

    monkeypatch.setattr(st, "success", mock_success)

    admin_app._tab_units_v2(client, "token")

    # Missing rows is the second expander. In the new code, if missing_rows is empty, st.success is called.
    assert success_called, "Should show success message when no bindings are missing"
    assert len(captured_dfs) == 1, "Only current bindings dataframe should be shown"


def test_units_filter_by_project_includes_global_bindings(monkeypatch, fake_state):
    """BUG-2: Filter by project should still show global bindings."""
    client = MagicMock()
    client.request.side_effect = [
        [
            {"project_id": "p1", "project_key": "P1", "project_name": "Project 1"}
        ],  # projects
        [
            {"calc_code": "c1", "unit_code": "u1", "requires_unit_binding": "required"}
        ],  # contracts
        [
            {"project_id": "p1", "unit_code": "u1", "source_field_id": "f1"},
            {"project_id": None, "unit_code": "u2", "source_field_id": "f2"},
            {"project_id": "p2", "unit_code": "u1", "source_field_id": "f3"},
        ],  # all_units
        [],  # field-keys
    ]

    mock_streamlit_common(monkeypatch)
    # Set project filter to p1
    monkeypatch.setattr(admin_app, "_project_filter", MagicMock(return_value="p1"))

    captured_dfs = []

    def mock_dataframe(data, **kwargs):
        captured_dfs.append(data)

    monkeypatch.setattr(st, "dataframe", mock_dataframe)

    admin_app._tab_units_v2(client, "token")

    # Current bindings is the first dataframe call
    current_bindings = captured_dfs[0]
    # Should include p1 AND None, but NOT p2
    # In new code, we have 'scope' column
    scopes = [u["scope"] for u in current_bindings]
    assert "P1" in scopes
    assert "Global (all projects)" in scopes
    assert len(current_bindings) == 2


def test_units_display_symbol_prefill_from_existing(monkeypatch, fake_state):
    """BUG-3: Display symbol should pre-fill from existing binding."""
    client = MagicMock()
    all_units = [
        {
            "project_id": "p1",
            "unit_code": "u1",
            "display_symbol": "CUSTOM_SYM",
            "source_field_id": "f1",
        }
    ]
    client.request.side_effect = [
        [
            {"project_id": "p1", "project_key": "P1", "project_name": "Project 1"}
        ],  # projects
        [
            {"calc_code": "c1", "unit_code": "u1", "requires_unit_binding": "required"}
        ],  # contracts
        all_units,  # all_units
        [],  # field-keys
    ]

    mock_streamlit_common(monkeypatch)
    monkeypatch.setattr(st, "dataframe", MagicMock())

    # Select project p1 and calc_code c1
    def mock_selectbox(label, options, **kwargs):
        if label == "Project":
            return "P1 - Project 1"
        if label == "Field Source Project":
            return [o for o in options if o != "All (NULL)"][0]
        return options[0]

    monkeypatch.setattr(st, "selectbox", mock_selectbox)
    monkeypatch.setattr(st, "multiselect", MagicMock(return_value=["c1"]))

    # Capture text_input call
    captured_text_inputs = {}

    def mock_text_input(label, value=None, **kwargs):
        captured_text_inputs[label] = value
        return value

    monkeypatch.setattr(st, "text_input", mock_text_input)

    admin_app._tab_units_v2(client, "token")

    assert captured_text_inputs["Display Symbol"] == "CUSTOM_SYM"


def test_units_missing_rows_deduplicated_by_unit_code(monkeypatch, fake_state):
    """New: missing_rows should be deduplicated by (project, unit_code)."""
    client = MagicMock()
    client.request.side_effect = [
        [
            {"project_id": "p1", "project_key": "P1", "project_name": "Project 1"}
        ],  # projects
        [
            {
                "calc_code": "velocity",
                "unit_code": "story_points",
                "requires_unit_binding": "required",
            },
            {
                "calc_code": "throughput",
                "unit_code": "story_points",
                "requires_unit_binding": "required",
            },
        ],  # contracts
        [],  # all_units (NOTHING CONFIGURED)
        [],  # field-keys
    ]

    mock_streamlit_common(monkeypatch)

    captured_dfs = []

    def mock_dataframe(data, **kwargs):
        captured_dfs.append(data)

    monkeypatch.setattr(st, "dataframe", mock_dataframe)

    admin_app._tab_units_v2(client, "token")

    # Missing rows is the second dataframe call
    missing_rows = captured_dfs[1]
    assert len(missing_rows) == 1, "Should only have ONE row for story_points"
    assert missing_rows[0]["unit_code"] == "story_points"
    assert "velocity" in missing_rows[0]["required_by"]
    assert "throughput" in missing_rows[0]["required_by"]
    assert missing_rows[0]["project_key"] == "P1"
