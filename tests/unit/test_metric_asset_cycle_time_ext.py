from datetime import datetime

import polars as pl

from pipelines.assets.metrics import cycle_time_ext


class _DummyDatabase:
    def __init__(self, engine):
        self._engine = engine

    def get_engine(self):
        return self._engine


def _asset_fn(defn):
    return defn.node_def.compute_fn.decorated_fn


def test_calculate_cycle_time_extended_skipped_when_no_issues(monkeypatch):
    monkeypatch.setattr(cycle_time_ext, "read_table", lambda *_a, **_k: pl.DataFrame())
    out = _asset_fn(cycle_time_ext.calculate_cycle_time_extended)(
        None, _DummyDatabase(object())
    )
    assert out["status"] == "skipped"


def test_calculate_cycle_time_extended_no_data_when_no_rules(monkeypatch):
    monkeypatch.setattr(cycle_time_ext, "get_project_agg_id", lambda *_a, **_k: "agg-1")
    monkeypatch.setattr(
        cycle_time_ext, "get_calculation_id", lambda *_a, **_k: "metric"
    )

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.issues" in query:
            return pl.DataFrame(
                {
                    "id": ["I1"],
                    "project_id": ["P1"],
                    "issue_key": ["P1-1"],
                    "created_at": [datetime(2026, 1, 1)],
                    "issue_type_id": ["T1"],
                    "parent_id": [None],
                }
            )
        if "FROM clean_jira.issue_status_changelog" in query:
            return pl.DataFrame({"issue_id": [], "to_status_id": [], "changed_at": []})
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
        if "FROM clean_jira.boards" in query:
            return pl.DataFrame({"id": ["B1"], "project_id": ["P1"]})
        raise AssertionError(query)

    monkeypatch.setattr(cycle_time_ext, "read_table", _read_table)
    monkeypatch.setattr(
        cycle_time_ext,
        "load_commitment_rules_for_calc",
        lambda *_a, **_k: pl.DataFrame(),
    )

    out = _asset_fn(cycle_time_ext.calculate_cycle_time_extended)(
        None, _DummyDatabase(object())
    )
    assert out["status"] == "no_data"


def test_calculate_cycle_time_extended_success(monkeypatch):
    calc_ids = {
        "issue_lifetime_days": "m1",
        "cycle_time_custom": "m2",
        "epic_delivery_time": "m3",
    }
    monkeypatch.setattr(
        cycle_time_ext, "get_calculation_id", lambda _e, code: calc_ids[code]
    )
    monkeypatch.setattr(cycle_time_ext, "get_project_agg_id", lambda *_a, **_k: "agg-1")
    monkeypatch.setattr(
        cycle_time_ext, "write_fact_values", lambda df, *_a, **_k: df.height
    )
    monkeypatch.setattr(
        cycle_time_ext,
        "load_commitment_rules_for_calc",
        lambda *_a, **_k: pl.DataFrame({"r": [1]}),
    )
    monkeypatch.setattr(
        cycle_time_ext, "resolve_rule_from_cache", lambda *_a, **_k: {"id": "r1"}
    )
    monkeypatch.setattr(
        cycle_time_ext,
        "identify_commitment_points_from_rule",
        lambda *_a, **_k: {"start_status_ids": ["START"], "end_status_ids": ["DONE"]},
    )

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.issues" in query:
            return pl.DataFrame(
                {
                    "id": ["I1", "E1"],
                    "project_id": ["P1", "P1"],
                    "issue_key": ["P1-1", "P1-EP1"],
                    "created_at": [datetime(2026, 1, 1), datetime(2026, 1, 1)],
                    "issue_type_id": ["T1", "T2"],
                    "parent_id": ["E1", None],
                }
            )
        if "FROM clean_jira.issue_status_changelog" in query:
            return pl.DataFrame(
                {
                    "issue_id": ["I1"],
                    "to_status_id": ["DONE"],
                    "changed_at": [datetime(2026, 1, 5)],
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
        if "FROM clean_jira.boards" in query:
            return pl.DataFrame({"id": ["B1"], "project_id": ["P1"]})
        raise AssertionError(query)

    monkeypatch.setattr(cycle_time_ext, "read_table", _read_table)
    monkeypatch.setattr(
        cycle_time_ext.cycle_logic,
        "calculate_issue_lifetime",
        lambda *_a, **_k: pl.DataFrame(
            {
                "project_id": ["P1"],
                "done_date": [datetime(2026, 1, 5)],
                "lifetime_days": [4.0],
                "id": ["I1"],
            }
        ),
    )
    monkeypatch.setattr(
        cycle_time_ext.cycle_logic,
        "calculate_cycle_time_custom",
        lambda *_a, **_k: pl.DataFrame(
            {
                "project_id": ["P1"],
                "end_at": [datetime(2026, 1, 5)],
                "cycle_days": [2.0],
                "id": ["I1"],
            }
        ),
    )
    monkeypatch.setattr(
        cycle_time_ext.cycle_logic,
        "calculate_epic_delivery_time",
        lambda *_a, **_k: pl.DataFrame(
            {
                "project_id": ["P1"],
                "epic_end": [datetime(2026, 1, 6)],
                "delivery_days": [5.0],
                "epic_id": ["E1"],
            }
        ),
    )

    out = _asset_fn(cycle_time_ext.calculate_cycle_time_extended)(
        None, _DummyDatabase(object())
    )
    assert out["status"] == "success"
    assert out["rows_written"] == 3


def test_cycle_time_ext_data_quality_check_fail_and_pass(monkeypatch):
    monkeypatch.setattr(cycle_time_ext, "get_calculation_id", lambda *_a, **_k: "m1")
    monkeypatch.setattr(
        cycle_time_ext, "read_table", lambda *_a, **_k: pl.DataFrame({"cnt": [2]})
    )
    failed = _asset_fn(cycle_time_ext.cycle_time_ext_data_quality_check)(
        _DummyDatabase(object())
    )
    assert failed.passed is False

    monkeypatch.setattr(
        cycle_time_ext, "read_table", lambda *_a, **_k: pl.DataFrame({"cnt": [0]})
    )
    passed = _asset_fn(cycle_time_ext.cycle_time_ext_data_quality_check)(
        _DummyDatabase(object())
    )
    assert passed.passed is True
