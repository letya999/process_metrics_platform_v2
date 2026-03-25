from datetime import datetime

import polars as pl

from pipelines.assets.metrics import time_to_market


class _DummyLog:
    def info(self, *_args, **_kwargs):
        return None


class _DummyContext:
    def __init__(self):
        self.log = _DummyLog()


class _DummyDatabase:
    def __init__(self, engine):
        self._engine = engine

    def get_engine(self):
        return self._engine


def _asset_fn(defn):
    return defn.node_def.compute_fn.decorated_fn


def test_calculate_time_to_market_deterministic_multiboard_pick(monkeypatch):
    monkeypatch.setattr(
        time_to_market, "get_definition_id", lambda *_args, **_kwargs: "def-ttm"
    )
    monkeypatch.setattr(
        time_to_market, "get_calculation_id", lambda *_args, **_kwargs: "m-ttm"
    )
    monkeypatch.setattr(
        time_to_market, "get_project_agg_id", lambda *_args, **_kwargs: "agg-1"
    )
    monkeypatch.setattr(
        time_to_market.ttm_logic,
        "load_issue_type_filter",
        lambda *_args, **_kwargs: ["Epic"],
    )
    monkeypatch.setattr(
        time_to_market,
        "load_commitment_rules_for_calc",
        lambda *_args, **_kwargs: [{"id": "r1"}],
    )
    monkeypatch.setattr(
        time_to_market,
        "resolve_rule_from_cache",
        lambda _rules, _p_id, b_id: (
            {
                "commitment_rule_id": "rule-b2",
                "start_column_id": "c2",
                "end_column_id": "c3",
            }
            if b_id == "B2"
            else None
        ),
    )
    monkeypatch.setattr(
        time_to_market,
        "identify_commitment_points_heuristic",
        lambda *_args, **_kwargs: {
            "middle_status_ids": ["MID1"],
            "end_status_ids": ["DONE1"],
            "commitment_rule_id": None,
        },
    )
    monkeypatch.setattr(
        time_to_market,
        "identify_commitment_points_from_rule",
        lambda *_args, **_kwargs: {
            "middle_status_ids": ["MID2"],
            "end_status_ids": ["DONE2"],
            "commitment_rule_id": "rule-b2",
        },
    )

    def _lead_time_calc(_issues, _status, middle_status_ids, _end_status_ids):
        if middle_status_ids == ["MID1"]:
            return pl.DataFrame(
                {
                    "issue_id": ["i1"],
                    "project_id": ["p1"],
                    "issue_key": ["P1-1"],
                    "commitment_start_at": [datetime(2026, 1, 1)],
                    "commitment_end_at": [datetime(2026, 1, 2)],
                    "lead_time_days": [1.0],
                }
            )
        return pl.DataFrame(
            {
                "issue_id": ["i1"],
                "project_id": ["p1"],
                "issue_key": ["P1-1"],
                "commitment_start_at": [datetime(2026, 1, 3)],
                "commitment_end_at": [datetime(2026, 1, 4)],
                "lead_time_days": [1.0],
            }
        )

    monkeypatch.setattr(
        time_to_market.lead_time_logic, "calculate_lead_time_per_issue", _lead_time_calc
    )

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.issues i" in query:
            return pl.DataFrame(
                {
                    "id": ["i1"],
                    "project_id": ["p1"],
                    "key": ["P1-1"],
                    "type_name": ["Epic"],
                    "jira_created_at": [datetime(2026, 1, 1)],
                    "jira_resolved_at": [datetime(2026, 1, 4)],
                    "project_key": ["P1"],
                }
            )
        if "FROM clean_jira.issue_status_changelog" in query:
            return pl.DataFrame(
                {
                    "issue_id": ["i1"],
                    "from_status_id": [None],
                    "to_status_id": ["DONE1"],
                    "changed_at": [datetime(2026, 1, 4)],
                }
            )
        if "FROM clean_jira.boards" in query:
            return pl.DataFrame(
                {"id": ["B1", "B2"], "project_id": ["p1", "p1"], "name": ["B1", "B2"]}
            )
        if "FROM clean_jira.board_columns bc" in query:
            return pl.DataFrame(
                {
                    "id": ["c1", "c2", "c3"],
                    "board_id": ["B1", "B2", "B2"],
                    "name": ["In Progress", "In Progress", "Done"],
                    "position": [1, 1, 2],
                    "status_id": ["MID1", "MID2", "DONE2"],
                }
            )
        if "FROM metrics.fact_values" in query:
            return pl.DataFrame({"cnt": [0]})
        raise AssertionError(query)

    monkeypatch.setattr(time_to_market, "read_table", _read_table)
    monkeypatch.setattr(
        time_to_market, "get_slice_rules", lambda *_args, **_kwargs: pl.DataFrame()
    )

    captured = {}

    def _write(df, *_args, **_kwargs):
        captured["df"] = df
        return df.height

    monkeypatch.setattr(time_to_market, "write_fact_values", _write)

    out = _asset_fn(time_to_market.calculate_time_to_market)(
        _DummyContext(), _DummyDatabase(object())
    )

    assert out["status"] == "success"
    assert out["rows_written"] == 1
    assert captured["df"][0, "entity_id"] == "P1-1"
    assert captured["df"][0, "commitment_rule_id"] == "rule-b2"
