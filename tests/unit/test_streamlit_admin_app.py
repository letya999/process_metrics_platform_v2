from contextlib import nullcontext
from unittest.mock import MagicMock

import pytest

import streamlit_admin.app as admin_app


class SessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


@pytest.fixture
def fake_state(monkeypatch):
    state = SessionState()
    monkeypatch.setattr(admin_app.st, "session_state", state)
    # Mock query_params to avoid errors
    monkeypatch.setattr(admin_app.st, "query_params", {})
    return state


def test_ensure_state_sets_defaults(fake_state):
    admin_app._ensure_state()

    assert fake_state["token"] is None
    assert fake_state["me"] is None


def test_login_view_success(monkeypatch, fake_state):
    client = MagicMock()
    client.request.side_effect = [
        {"access_token": "t1"},
        {"email": "admin@example.com"},
    ]
    rerun = MagicMock()

    monkeypatch.setattr(admin_app.st, "title", MagicMock())
    monkeypatch.setattr(admin_app.st, "caption", MagicMock())
    monkeypatch.setattr(admin_app.st, "form", lambda _name: nullcontext())
    monkeypatch.setattr(
        admin_app.st,
        "text_input",
        lambda label, **_kwargs: "e" if label == "Email" else "p",
    )
    monkeypatch.setattr(
        admin_app.st, "form_submit_button", lambda *_args, **_kwargs: True
    )
    monkeypatch.setattr(admin_app.st, "rerun", rerun)

    admin_app._login_view(client)

    assert fake_state.token == "t1"
    assert fake_state.me == {"email": "admin@example.com"}
    # Verify query_params NOT used
    assert "admin_token" not in admin_app.st.query_params
    rerun.assert_called_once()


def test_logout_clears_state(monkeypatch, fake_state):
    fake_state.token = "tok"
    fake_state.me = {"email": "admin@example.com"}
    client = MagicMock()
    rerun = MagicMock()

    monkeypatch.setattr(admin_app.st, "rerun", rerun)

    admin_app._logout(client)

    client.request.assert_called_once_with("POST", "/admin/auth/logout", token="tok")
    assert fake_state.token is None
    assert fake_state.me is None
    # Verify query_params NOT used
    assert "admin_token" not in admin_app.st.query_params
    rerun.assert_called_once()


def test_tab_validate_success(monkeypatch):
    client = MagicMock()
    client.request.return_value = {"issues": [{"code": "x"}]}
    dataframe = MagicMock()
    show_success = MagicMock()

    monkeypatch.setattr(admin_app, "section_title", MagicMock())
    monkeypatch.setattr(admin_app.st, "button", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(admin_app.st, "dataframe", dataframe)
    monkeypatch.setattr(admin_app, "show_success", show_success)

    admin_app._tab_validate(client, "token", "pid")

    dataframe.assert_called_once()
    show_success.assert_called_once()


def test_main_renders_tabs_when_authenticated(monkeypatch, fake_state):
    fake_state.token = "tok"
    fake_state.me = {"email": "admin@example.com"}
    client = MagicMock()

    monkeypatch.setattr(admin_app, "get_client", lambda: client)
    monkeypatch.setattr(admin_app.st, "sidebar", nullcontext())
    monkeypatch.setattr(admin_app.st, "markdown", MagicMock())
    monkeypatch.setattr(admin_app.st, "write", MagicMock())
    monkeypatch.setattr(admin_app.st, "button", lambda *_args, **_kwargs: False)

    # Patch tabs to return enough tabs for _page_configuration
    monkeypatch.setattr(
        admin_app.st, "tabs", lambda _labels: [nullcontext() for _ in range(9)]
    )

    called = []
    monkeypatch.setattr(
        admin_app, "_tab_integrations", lambda *_args: called.append("integrations")
    )
    monkeypatch.setattr(
        admin_app, "_tab_metrics_catalog", lambda *_args: called.append("catalog")
    )
    monkeypatch.setattr(
        admin_app, "_tab_commitment_v2", lambda *_args: called.append("commitment")
    )
    monkeypatch.setattr(
        admin_app, "_tab_settings_v2", lambda *_args: called.append("settings")
    )
    monkeypatch.setattr(
        admin_app, "_tab_units_v2", lambda *_args: called.append("units")
    )
    monkeypatch.setattr(
        admin_app, "_tab_slices_v2", lambda *_args: called.append("slices")
    )
    monkeypatch.setattr(
        admin_app, "_tab_validate", lambda *_args: called.append("validate")
    )
    monkeypatch.setattr(admin_app, "_tab_jobs", lambda *_args: called.append("jobs"))
    monkeypatch.setattr(
        admin_app, "_tab_metrics_run", lambda *_args: called.append("metrics_run")
    )

    admin_app.main()

    assert called == [
        "integrations",
        "catalog",
        "commitment",
        "settings",
        "units",
        "slices",
        "validate",
        "jobs",
        "metrics_run",
    ]


def test_main_always_routes_to_page_configuration(monkeypatch, fake_state):
    fake_state.token = "tok"
    fake_state.me = {"email": "admin@example.com"}
    client = MagicMock()

    monkeypatch.setattr(admin_app, "get_client", lambda: client)
    monkeypatch.setattr(admin_app.st, "sidebar", nullcontext())
    monkeypatch.setattr(admin_app.st, "markdown", MagicMock())
    monkeypatch.setattr(admin_app.st, "write", MagicMock())
    monkeypatch.setattr(admin_app.st, "button", lambda *_args, **_kwargs: False)

    called = []
    monkeypatch.setattr(
        admin_app, "_page_configuration", lambda *_args: called.append("config")
    )

    admin_app.main()
    assert called == ["config"]


def test_tab_metrics_catalog_bulk_fetch(monkeypatch):
    client = MagicMock()
    client.request.side_effect = [
        [{"project_id": "p1", "project_key": "P1"}],  # projects
        [{"calc_code": "c1", "metric_code": "m1"}],  # contracts
        [{"calc_code": "c1", "project_id": "p1"}],  # all_settings
        [],  # all_commitment_rules
        [],  # all_units
    ]

    monkeypatch.setattr(admin_app, "section_title", MagicMock())
    monkeypatch.setattr(admin_app.st, "dataframe", MagicMock())
    monkeypatch.setattr(admin_app.st, "markdown", MagicMock())

    admin_app._tab_metrics_catalog(client, "token")

    # Verify bulk calls (projects, contracts, settings, rules, units)
    assert client.request.call_count == 5
    # Verify no per-project calls in loop
