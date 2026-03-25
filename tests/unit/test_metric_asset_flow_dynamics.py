from datetime import datetime

import polars as pl
import pytest

from pipelines.assets.metrics import flow_dynamics


class _DummyDatabase:
    def __init__(self, engine):
        self._engine = engine

    def get_engine(self):
        return self._engine


class _DummyLog:
    def info(self, *_args, **_kwargs):
        return None


class _DummyContext:
    def __init__(self):
        self.log = _DummyLog()


def _asset_fn(defn):
    return defn.node_def.compute_fn.decorated_fn


@pytest.fixture(autouse=True)
def _stub_definition_id(monkeypatch):
    monkeypatch.setattr(flow_dynamics, "get_definition_id", lambda *_a, **_k: "def-fd")
    monkeypatch.setattr(flow_dynamics, "get_calculation_id", lambda *_a, **_k: "metric")


def test_calculate_flow_dynamics_skipped(monkeypatch):
    monkeypatch.setattr(flow_dynamics, "read_table", lambda *_a, **_k: pl.DataFrame())
    out = _asset_fn(flow_dynamics.calculate_flow_dynamics)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert out["status"] == "skipped"


def test_calculate_flow_dynamics_no_data(monkeypatch):
    monkeypatch.setattr(flow_dynamics, "get_project_agg_id", lambda *_a, **_k: "agg-1")
    monkeypatch.setattr(flow_dynamics, "get_calculation_id", lambda _e, _c: "metric")

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.sprints" in query:
            return pl.DataFrame(
                {
                    "id": ["S1"],
                    "project_id": ["P1"],
                    "start_date": [datetime(2026, 1, 1)],
                }
            )
        if "FROM clean_jira.sprint_issues" in query:
            return pl.DataFrame({"issue_id": ["I1"], "sprint_id": ["S1"]})
        if "FROM clean_jira.issue_status_changelog" in query:
            return pl.DataFrame({"issue_id": [], "to_status_id": [], "changed_at": []})
        if "FROM clean_jira.field_value_changelog" in query:
            return pl.DataFrame(
                {
                    "issue_id": [],
                    "field_key_id": [],
                    "old_value": [],
                    "new_value": [],
                    "change_time": [],
                }
            )
        if "FROM clean_jira.issues i" in query:
            return pl.DataFrame(
                {"id": ["I1"], "project_id": ["P1"], "type_name": ["Task"]}
            )
        if "FROM metrics.calculation_settings" in query:
            return pl.DataFrame()
        raise AssertionError(query)

    monkeypatch.setattr(flow_dynamics, "read_table", _read_table)
    out = _asset_fn(flow_dynamics.calculate_flow_dynamics)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert out["status"] == "no_data"


def test_calculate_flow_dynamics_success(monkeypatch):
    calc_ids = {"daily_status_entry_count": "m1", "field_change_count": "m2"}
    monkeypatch.setattr(flow_dynamics, "get_calculation_id", lambda _e, c: calc_ids[c])
    monkeypatch.setattr(flow_dynamics, "get_project_agg_id", lambda *_a, **_k: "agg-1")
    monkeypatch.setattr(
        flow_dynamics, "write_fact_values", lambda df, *_a, **_k: df.height
    )

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.sprints" in query:
            return pl.DataFrame(
                {
                    "id": ["S1"],
                    "project_id": ["P1"],
                    "start_date": [datetime(2026, 1, 1)],
                }
            )
        if "FROM clean_jira.sprint_issues" in query:
            return pl.DataFrame({"issue_id": ["I1"], "sprint_id": ["S1"]})
        if "FROM clean_jira.issue_status_changelog" in query:
            return pl.DataFrame(
                {
                    "issue_id": ["I1"],
                    "to_status_id": ["In Progress"],
                    "changed_at": [datetime(2026, 1, 2)],
                }
            )
        if "FROM clean_jira.field_value_changelog" in query:
            return pl.DataFrame(
                {
                    "issue_id": ["I1"],
                    "field_key_id": ["f1"],
                    "old_value": ["1"],
                    "new_value": ["2"],
                    "change_time": [datetime(2026, 1, 3)],
                }
            )
        if "FROM clean_jira.issues i" in query:
            return pl.DataFrame(
                {"id": ["I1"], "project_id": ["P1"], "type_name": ["Task"]}
            )
        if "FROM metrics.calculation_settings" in query and params["calc_id"] == "m1":
            return pl.DataFrame(
                {
                    "id": ["set1"],
                    "project_id": [None],
                    "settings_json": [{"target_status": "In Progress"}],
                }
            )
        if "FROM metrics.calculation_settings" in query and params["calc_id"] == "m2":
            return pl.DataFrame(
                {
                    "id": ["set2"],
                    "project_id": [None],
                    "settings_json": [{"field_key_id": "f1"}],
                }
            )
        raise AssertionError(query)

    monkeypatch.setattr(flow_dynamics, "read_table", _read_table)
    monkeypatch.setattr(
        flow_dynamics.flow_dynamics_logic,
        "calculate_daily_status_entry",
        lambda *_a, **_k: pl.DataFrame(
            {
                "project_id": ["P1"],
                "time_date": [datetime(2026, 1, 2)],
                "entry_count": [1],
                "iteration_id": ["S1"],
            }
        ),
    )
    monkeypatch.setattr(
        flow_dynamics.flow_dynamics_logic,
        "calculate_field_change_count",
        lambda *_a, **_k: pl.DataFrame(
            {
                "project_id": ["P1"],
                "start_date": [datetime(2026, 1, 1)],
                "change_count": [2],
                "iteration_id": ["S1"],
            }
        ),
    )

    out = _asset_fn(flow_dynamics.calculate_flow_dynamics)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert out["status"] == "success"
    assert out["rows_written"] == 2
    assert out["metrics_calculated"] == 2


def test_flow_dynamics_data_quality_check_fail_and_pass(monkeypatch):
    monkeypatch.setattr(flow_dynamics, "get_calculation_id", lambda *_a, **_k: "m1")
    monkeypatch.setattr(
        flow_dynamics, "read_table", lambda *_a, **_k: pl.DataFrame({"cnt": [1]})
    )
    failed = _asset_fn(flow_dynamics.flow_dynamics_data_quality_check)(
        _DummyDatabase(object())
    )
    assert failed.passed is False

    monkeypatch.setattr(
        flow_dynamics, "read_table", lambda *_a, **_k: pl.DataFrame({"cnt": [0]})
    )
    passed = _asset_fn(flow_dynamics.flow_dynamics_data_quality_check)(
        _DummyDatabase(object())
    )
    assert passed.passed is True
