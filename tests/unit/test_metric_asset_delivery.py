from datetime import datetime

import polars as pl
import pytest

from pipelines.assets.metrics import delivery


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
    monkeypatch.setattr(delivery, "get_definition_id", lambda *_a, **_k: "def-d")
    monkeypatch.setattr(delivery, "get_calculation_id", lambda *_a, **_k: "metric")


def test_calculate_delivery_metrics_skipped(monkeypatch):
    monkeypatch.setattr(delivery, "read_table", lambda *_a, **_k: pl.DataFrame())
    out = _asset_fn(delivery.calculate_delivery_metrics)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert out["status"] == "skipped"


def test_calculate_delivery_metrics_no_data(monkeypatch):
    monkeypatch.setattr(delivery, "get_project_agg_id", lambda *_a, **_k: "agg-p1")
    monkeypatch.setattr(delivery, "get_calculation_id", lambda *_a, **_k: "metric")
    monkeypatch.setattr(
        delivery, "load_commitment_rules_for_calc", lambda *_a, **_k: pl.DataFrame()
    )
    monkeypatch.setattr(delivery, "resolve_rule_from_cache", lambda *_a, **_k: None)

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.issues" in query:
            return pl.DataFrame(
                {
                    "id": ["I1"],
                    "project_id": ["P1"],
                    "type_name": ["Task"],
                    "created_at": [datetime(2026, 1, 1)],
                }
            )
        if "FROM clean_jira.issue_status_changelog" in query:
            return pl.DataFrame({"issue_id": [], "to_status_id": [], "changed_at": []})
        if "FROM clean_jira.field_keys" in query:
            return pl.DataFrame({"id": ["SP"], "name": ["Story Points"]})
        if "FROM clean_jira.field_values" in query:
            return pl.DataFrame({"issue_id": [], "field_key_id": [], "json_value": []})
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
        if "FROM clean_jira.board_columns bc" in query:
            return pl.DataFrame(
                {
                    "id": ["C1"],
                    "board_id": ["B1"],
                    "name": ["Done"],
                    "status_id": ["DONE"],
                    "position": [1],
                }
            )
        if "SELECT * FROM clean_jira.boards" in query:
            return pl.DataFrame({"id": ["B1"], "project_id": ["P1"]})
        if "FROM clean_jira.release_issues" in query:
            return pl.DataFrame({"issue_id": [], "version_name": []})
        raise AssertionError(query)

    monkeypatch.setattr(delivery, "read_table", _read_table)
    out = _asset_fn(delivery.calculate_delivery_metrics)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert out["status"] == "no_data"


def test_calculate_delivery_metrics_success(monkeypatch):
    calc_ids = {
        "release_burnup_scope_sp": "m_scope",
        "release_burnup_done_sp": "m_done",
    }
    monkeypatch.setattr(delivery, "get_calculation_id", lambda _e, code: calc_ids[code])
    monkeypatch.setattr(delivery, "get_project_agg_id", lambda *_a, **_k: "agg-p1")
    monkeypatch.setattr(delivery, "write_fact_values", lambda df, *_a, **_k: df.height)
    monkeypatch.setattr(
        delivery,
        "load_commitment_rules_for_calc",
        lambda *_a, **_k: pl.DataFrame({"r": [1]}),
    )
    monkeypatch.setattr(
        delivery, "resolve_rule_from_cache", lambda *_a, **_k: {"id": "r1"}
    )
    monkeypatch.setattr(
        delivery,
        "identify_commitment_points_from_rule",
        lambda *_a, **_k: {"end_status_ids": ["DONE"]},
    )
    monkeypatch.setattr(
        delivery.delivery_logic,
        "calculate_release_burnup",
        lambda *_a, **_k: pl.DataFrame(
            {
                "project_id": ["P1"],
                "time_date": [datetime(2026, 1, 3)],
                "scope_sp": [8.0],
                "done_sp": [5.0],
                "version_name": ["1.0"],
            }
        ),
    )

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.issues" in query:
            return pl.DataFrame(
                {
                    "id": ["I1"],
                    "project_id": ["P1"],
                    "type_name": ["Task"],
                    "created_at": [datetime(2026, 1, 1)],
                }
            )
        if "FROM clean_jira.issue_status_changelog" in query:
            return pl.DataFrame({"issue_id": ["I1"], "to_status_id": ["DONE"]})
        if "FROM clean_jira.field_keys" in query:
            return pl.DataFrame({"id": ["SP"], "name": ["Story Points"]})
        if "FROM clean_jira.field_values" in query:
            return pl.DataFrame(
                {"issue_id": ["I1"], "field_key_id": ["SP"], "json_value": ["5"]}
            )
        if "FROM clean_jira.field_value_changelog" in query:
            return pl.DataFrame(
                {
                    "issue_id": ["I1"],
                    "field_key_id": ["SP"],
                    "old_value": ["3"],
                    "new_value": ["5"],
                    "change_time": [datetime(2026, 1, 2)],
                }
            )
        if "FROM clean_jira.board_columns bc" in query:
            return pl.DataFrame(
                {
                    "id": ["C1"],
                    "board_id": ["B1"],
                    "name": ["Done"],
                    "status_id": ["DONE"],
                    "position": [1],
                }
            )
        if "SELECT * FROM clean_jira.boards" in query:
            return pl.DataFrame({"id": ["B1"], "project_id": ["P1"]})
        if "FROM clean_jira.release_issues" in query:
            return pl.DataFrame({"issue_id": ["I1"], "version_name": ["1.0"]})
        raise AssertionError(query)

    monkeypatch.setattr(delivery, "read_table", _read_table)
    out = _asset_fn(delivery.calculate_delivery_metrics)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert out["status"] == "success"
    assert out["rows_written"] == 2


def test_delivery_data_quality_check_fail_and_pass(monkeypatch):
    monkeypatch.setattr(delivery, "get_calculation_id", lambda *_a, **_k: "m_scope")
    monkeypatch.setattr(
        delivery, "read_table", lambda *_a, **_k: pl.DataFrame({"cnt": [1]})
    )
    failed = _asset_fn(delivery.delivery_data_quality_check)(_DummyDatabase(object()))
    assert failed.passed is False

    monkeypatch.setattr(
        delivery, "read_table", lambda *_a, **_k: pl.DataFrame({"cnt": [0]})
    )
    passed = _asset_fn(delivery.delivery_data_quality_check)(_DummyDatabase(object()))
    assert passed.passed is True
