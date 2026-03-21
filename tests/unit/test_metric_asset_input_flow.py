from datetime import datetime

import polars as pl

from pipelines.assets.metrics import input_flow


class _DummyDatabase:
    def __init__(self, engine):
        self._engine = engine

    def get_engine(self):
        return self._engine


def _asset_fn(defn):
    return defn.node_def.compute_fn.decorated_fn


def test_calculate_input_flow_skipped(monkeypatch):
    monkeypatch.setattr(input_flow, "read_table", lambda *_a, **_k: pl.DataFrame())
    out = _asset_fn(input_flow.calculate_input_flow)(None, _DummyDatabase(object()))
    assert out["status"] == "skipped"


def test_calculate_input_flow_no_data(monkeypatch):
    monkeypatch.setattr(input_flow, "get_calculation_id", lambda *_a, **_k: "m1")
    monkeypatch.setattr(input_flow, "get_project_agg_id", lambda *_a, **_k: "agg-1")
    monkeypatch.setattr(
        input_flow,
        "load_commitment_rules_for_calc",
        lambda *_a, **_k: pl.DataFrame({"r": [1]}),
    )
    monkeypatch.setattr(input_flow, "resolve_rule_from_cache", lambda *_a, **_k: None)

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.issues" in query:
            return pl.DataFrame({"id": ["I1"], "project_id": ["P1"]})
        if "FROM clean_jira.issue_status_changelog" in query:
            return pl.DataFrame({"issue_id": [], "to_status_id": [], "changed_at": []})
        if "FROM clean_jira.board_columns bc" in query:
            return pl.DataFrame(
                {
                    "id": ["C1"],
                    "board_id": ["B1"],
                    "name": ["In Progress"],
                    "status_id": ["INPROG"],
                    "position": [1],
                }
            )
        if "FROM clean_jira.boards" in query:
            return pl.DataFrame({"id": ["B1"], "project_id": ["P1"]})
        raise AssertionError(query)

    monkeypatch.setattr(input_flow, "read_table", _read_table)
    out = _asset_fn(input_flow.calculate_input_flow)(None, _DummyDatabase(object()))
    assert out["status"] == "no_data"


def test_calculate_input_flow_success(monkeypatch):
    monkeypatch.setattr(input_flow, "get_calculation_id", lambda *_a, **_k: "m1")
    monkeypatch.setattr(input_flow, "get_project_agg_id", lambda *_a, **_k: "agg-1")
    monkeypatch.setattr(
        input_flow, "write_fact_values", lambda df, *_a, **_k: df.height
    )
    monkeypatch.setattr(
        input_flow,
        "load_commitment_rules_for_calc",
        lambda *_a, **_k: pl.DataFrame({"r": [1]}),
    )
    monkeypatch.setattr(
        input_flow, "resolve_rule_from_cache", lambda *_a, **_k: {"id": "r1"}
    )
    monkeypatch.setattr(
        input_flow,
        "identify_commitment_points_from_rule",
        lambda *_a, **_k: {"start_status_ids": ["INPROG"]},
    )

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.issues" in query:
            return pl.DataFrame({"id": ["I1"], "project_id": ["P1"]})
        if "FROM clean_jira.issue_status_changelog" in query:
            return pl.DataFrame(
                {
                    "issue_id": ["I1"],
                    "to_status_id": ["INPROG"],
                    "changed_at": [datetime(2026, 1, 2)],
                }
            )
        if "FROM clean_jira.board_columns bc" in query:
            return pl.DataFrame(
                {
                    "id": ["C1"],
                    "board_id": ["B1"],
                    "name": ["In Progress"],
                    "status_id": ["INPROG"],
                    "position": [1],
                }
            )
        if "FROM clean_jira.boards" in query:
            return pl.DataFrame({"id": ["B1"], "project_id": ["P1"]})
        raise AssertionError(query)

    monkeypatch.setattr(input_flow, "read_table", _read_table)
    monkeypatch.setattr(
        input_flow.input_flow_logic,
        "calculate_input_flow_weekly",
        lambda *_a, **_k: pl.DataFrame(
            {
                "project_id": ["P1"],
                "iso_week_start_date": [datetime(2025, 12, 29)],
                "flow_count": [2],
            }
        ),
    )

    out = _asset_fn(input_flow.calculate_input_flow)(None, _DummyDatabase(object()))
    assert out["status"] == "success"
    assert out["rows_written"] == 1


def test_input_flow_data_quality_check_fail_and_pass(monkeypatch):
    monkeypatch.setattr(input_flow, "get_calculation_id", lambda *_a, **_k: "m1")
    monkeypatch.setattr(
        input_flow, "read_table", lambda *_a, **_k: pl.DataFrame({"cnt": [1]})
    )
    failed = _asset_fn(input_flow.input_flow_data_quality_check)(
        _DummyDatabase(object())
    )
    assert failed.passed is False

    monkeypatch.setattr(
        input_flow, "read_table", lambda *_a, **_k: pl.DataFrame({"cnt": [0]})
    )
    passed = _asset_fn(input_flow.input_flow_data_quality_check)(
        _DummyDatabase(object())
    )
    assert passed.passed is True
