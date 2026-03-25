from datetime import datetime

import polars as pl
import pytest

from pipelines.assets.metrics import aging_extended


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
    monkeypatch.setattr(aging_extended, "get_definition_id", lambda *_a, **_k: "def-a")
    monkeypatch.setattr(
        aging_extended, "get_calculation_id", lambda *_a, **_k: "metric"
    )


def test_calculate_aging_extended_skipped(monkeypatch):
    monkeypatch.setattr(aging_extended, "read_table", lambda *_a, **_k: pl.DataFrame())
    out = _asset_fn(aging_extended.calculate_aging_extended)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert out["status"] == "skipped"


def test_calculate_aging_extended_no_data(monkeypatch):
    monkeypatch.setattr(
        aging_extended, "get_project_agg_id", lambda *_a, **_k: "agg-p1"
    )
    monkeypatch.setattr(
        aging_extended, "get_calculation_id", lambda *_a, **_k: "metric"
    )
    monkeypatch.setattr(
        aging_extended,
        "load_commitment_rules_for_calc",
        lambda *_a, **_k: pl.DataFrame(),
    )
    monkeypatch.setattr(
        aging_extended, "resolve_rule_from_cache", lambda *_a, **_k: None
    )

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.issues" in query:
            return pl.DataFrame(
                {
                    "id": ["I1"],
                    "project_id": ["P1"],
                    "key": ["P1-1"],
                    "type_name": ["Task"],
                    "status_id": ["IN_PROGRESS"],
                    "updated_at": [datetime(2026, 1, 2)],
                }
            )
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
        if "SELECT * FROM clean_jira.field_keys" in query:
            return pl.DataFrame(
                {"id": ["SP"], "external_key": ["story_points"], "name": ["SP"]}
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
        raise AssertionError(query)

    monkeypatch.setattr(aging_extended, "read_table", _read_table)
    out = _asset_fn(aging_extended.calculate_aging_extended)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert out["status"] == "no_data"


def test_calculate_aging_extended_success(monkeypatch):
    calc_ids = {"blocked_time_total": "m_blocked", "stale_days": "m_stale"}
    monkeypatch.setattr(
        aging_extended, "get_calculation_id", lambda _e, code: calc_ids[code]
    )
    monkeypatch.setattr(
        aging_extended, "get_project_agg_id", lambda *_a, **_k: "agg-p1"
    )
    monkeypatch.setattr(
        aging_extended, "write_fact_values", lambda df, *_a, **_k: df.height
    )
    monkeypatch.setattr(
        aging_extended,
        "load_commitment_rules_for_calc",
        lambda *_a, **_k: pl.DataFrame({"rule": [1]}),
    )
    monkeypatch.setattr(
        aging_extended, "resolve_rule_from_cache", lambda *_a, **_k: {"id": "r1"}
    )
    monkeypatch.setattr(
        aging_extended,
        "identify_commitment_points_from_rule",
        lambda *_a, **_k: {"end_status_ids": ["DONE"]},
    )
    monkeypatch.setattr(
        aging_extended.aging_logic,
        "calculate_blocked_time",
        lambda *_a, **_k: pl.DataFrame(
            {"project_id": ["P1"], "issue_id": ["I1"], "blocked_hours": [4.0]}
        ),
    )
    monkeypatch.setattr(
        aging_extended.aging_logic,
        "calculate_stale_days",
        lambda *_a, **_k: pl.DataFrame(
            {"project_id": ["P1"], "issue_id": ["I1"], "stale_days": [2.0]}
        ),
    )

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.issues" in query:
            return pl.DataFrame(
                {
                    "id": ["I1"],
                    "project_id": ["P1"],
                    "key": ["P1-1"],
                    "type_name": ["Task"],
                    "status_id": ["IN_PROGRESS"],
                    "updated_at": [datetime(2026, 1, 2)],
                }
            )
        if "FROM clean_jira.issue_status_changelog" in query:
            return pl.DataFrame(
                {
                    "issue_id": ["I1"],
                    "to_status_id": ["DONE"],
                    "changed_at": [datetime(2026, 1, 3)],
                }
            )
        if "FROM clean_jira.field_value_changelog" in query:
            return pl.DataFrame(
                {
                    "issue_id": ["I1"],
                    "field_key_id": ["BL"],
                    "old_value": ["false"],
                    "new_value": ["true"],
                    "change_time": [datetime(2026, 1, 2)],
                }
            )
        if "SELECT * FROM clean_jira.field_keys" in query:
            return pl.DataFrame(
                {"id": ["BL"], "external_key": ["blocked"], "name": ["Blocked"]}
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
        raise AssertionError(query)

    monkeypatch.setattr(aging_extended, "read_table", _read_table)
    out = _asset_fn(aging_extended.calculate_aging_extended)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert out["status"] == "success"
    assert out["rows_written"] == 2


def test_aging_extended_data_quality_check_fail_and_pass(monkeypatch):
    monkeypatch.setattr(
        aging_extended, "get_calculation_id", lambda *_a, **_k: "m_stale"
    )
    monkeypatch.setattr(
        aging_extended, "read_table", lambda *_a, **_k: pl.DataFrame({"cnt": [1]})
    )
    failed = _asset_fn(aging_extended.aging_extended_data_quality_check)(
        _DummyDatabase(object())
    )
    assert failed.passed is False

    monkeypatch.setattr(
        aging_extended, "read_table", lambda *_a, **_k: pl.DataFrame({"cnt": [0]})
    )
    passed = _asset_fn(aging_extended.aging_extended_data_quality_check)(
        _DummyDatabase(object())
    )
    assert passed.passed is True
