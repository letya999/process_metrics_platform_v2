from datetime import date, datetime

import polars as pl

from pipelines.assets.metrics import (
    aging_extended,
    cumulative_flow,
    waste,
)


class _DummyLog:
    def info(self, *args, **kwargs):
        pass

    def debug(self, *args, **kwargs):
        pass


class _DummyContext:
    def __init__(self):
        self.log = _DummyLog()


class _DummyDatabase:
    def __init__(self, engine):
        self._engine = engine

    def get_engine(self):
        return self._engine


def _asset_fn(defn):
    if hasattr(defn, "node_def"):
        return defn.node_def.compute_fn.decorated_fn
    return defn


def test_cumulative_flow_slicing(monkeypatch):
    monkeypatch.setattr(cumulative_flow, "get_definition_id", lambda *_a: "def-cfd")
    monkeypatch.setattr(cumulative_flow, "get_calculation_id", lambda *_a: "calc-cfd")
    monkeypatch.setattr(
        cumulative_flow, "get_project_agg_id", lambda engine, pid: f"agg-{pid}"
    )
    captured = {"writes": []}

    def _write_fact_values(df, *_a, **_k):
        captured["writes"].append(df)
        return df.height

    monkeypatch.setattr(cumulative_flow, "write_fact_values", _write_fact_values)

    def _read_table(_e, query, params=None):
        if "FROM clean_jira.issues" in query:
            return pl.DataFrame(
                {
                    "id": ["i1"],
                    "project_id": ["p1"],
                    "type_name": ["Story"],
                    "status_id": ["s1"],
                    "jira_created_at": [datetime(2026, 1, 1)],
                    "project_key": ["P1"],
                }
            )
        if "FROM clean_jira.issue_status_changelog" in query:
            return pl.DataFrame(
                {
                    "issue_id": ["i1"],
                    "from_status_id": [None],
                    "to_status_id": ["s1"],
                    "changed_at": [datetime(2026, 1, 1)],
                }
            )
        if "FROM clean_jira.issue_statuses" in query:
            return pl.DataFrame(
                {
                    "id": ["s1"],
                    "project_id": ["p1"],
                    "name": ["To Do"],
                    "category": ["todo"],
                }
            )
        if "FROM clean_jira.boards" in query:
            return pl.DataFrame({"id": ["b1"], "project_id": ["p1"], "name": ["Board"]})
        if "FROM clean_jira.board_columns" in query:
            return pl.DataFrame(
                {
                    "id": ["c1"],
                    "board_id": ["b1"],
                    "name": ["To Do"],
                    "position": [1],
                    "status_id": ["s1"],
                }
            )
        return pl.DataFrame()

    monkeypatch.setattr(cumulative_flow, "read_table", _read_table)
    monkeypatch.setattr(
        cumulative_flow.cfd_logic,
        "calculate_cumulative_flow_diagram",
        lambda **_k: pl.DataFrame(
            {
                "project_id": ["p1"],
                "date": [date(2026, 1, 1)],
                "issue_count": [1],
                "column_id": ["c1"],
                "status_id": ["s1"],
            }
        ),
    )

    monkeypatch.setattr(
        cumulative_flow,
        "get_slice_rules",
        lambda *_a, **_k: pl.DataFrame(
            {
                "slice_rule_id": ["rule-1"],
                "slice_rule_name": ["By Type"],
                "group_by_column": ["issue_type"],
                "enabled": [True],
            }
        ),
    )

    def _fake_iter_slicing_cfd(*_a, **_k):
        yield pl.DataFrame(
            {
                "project_id": ["p1"],
                "date": [date(2026, 1, 1)],
                "issue_count": [1],
                "column_id": ["c1"],
                "status_id": ["s1"],
                "slice_value": ["Story"],
            }
        )

    monkeypatch.setattr(cumulative_flow, "iter_slicing_results", _fake_iter_slicing_cfd)

    out = _asset_fn(cumulative_flow.calculate_cumulative_flow_diagram)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert out["status"] == "success"
    assert out["rows_written"] == 2
    all_written = pl.concat(captured["writes"], how="diagonal_relaxed")
    assert "context_json" in all_written.columns
    assert all_written.get_column("context_json").null_count() == 0
    contexts = all_written.get_column("context_json").to_list()
    assert all(ctx["column_id"] == "c1" for ctx in contexts)
    assert all(ctx["column_name"] == "To Do" for ctx in contexts)
    assert all(ctx["status_id"] == "s1" for ctx in contexts)
    slice_values = all_written.get_column("slice_value").to_list()
    assert len(slice_values) == 2
    assert "Story" in slice_values
    assert None in slice_values


def test_aging_extended_slicing(monkeypatch):
    monkeypatch.setattr(aging_extended, "get_definition_id", lambda *_a: "def-aging")
    monkeypatch.setattr(
        aging_extended, "get_calculation_id", lambda _e, code: f"id-{code}"
    )
    monkeypatch.setattr(
        aging_extended, "get_project_agg_id", lambda engine, pid: f"agg-{pid}"
    )
    monkeypatch.setattr(
        aging_extended, "write_fact_values", lambda df, *_a, **_k: df.height
    )

    def _read_table(_e, query, params=None):
        if "FROM clean_jira.issues" in query:
            return pl.DataFrame(
                {
                    "id": ["i1"],
                    "project_id": ["p1"],
                    "key": ["K1"],
                    "type_name": ["Story"],
                    "status_id": ["s1"],
                    "updated_at": [datetime(2026, 1, 1)],
                }
            )
        if "FROM clean_jira.issue_status_changelog" in query:
            return pl.DataFrame(
                {
                    "issue_id": [],
                    "from_status_id": [],
                    "to_status_id": [],
                    "changed_at": [],
                }
            )
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
        if "FROM clean_jira.field_keys" in query:
            return pl.DataFrame(
                {"id": ["f1"], "external_key": ["blocked"], "name": ["Blocked"]}
            )
        if "FROM clean_jira.board_columns" in query:
            return pl.DataFrame(
                {
                    "id": ["c1"],
                    "board_id": ["b1"],
                    "name": ["Done"],
                    "status_id": ["s1"],
                    "position": [1],
                }
            )
        if "FROM clean_jira.boards" in query:
            return pl.DataFrame({"id": ["b1"], "project_id": ["p1"], "name": ["Board"]})
        return pl.DataFrame()

    monkeypatch.setattr(aging_extended, "read_table", _read_table)
    monkeypatch.setattr(
        aging_extended, "load_commitment_rules_for_calc", lambda *_a, **_k: []
    )
    monkeypatch.setattr(
        aging_extended.aging_logic,
        "calculate_blocked_time",
        lambda *_a: pl.DataFrame(
            {"project_id": ["p1"], "issue_id": ["i1"], "blocked_hours": [10.0]}
        ),
    )

    monkeypatch.setattr(
        aging_extended,
        "get_slice_rules",
        lambda *_a, **_k: pl.DataFrame(
            {"slice_rule_id": ["rule-1"], "enabled": [True]}
        ),
    )

    def _fake_iter_slicing_aging(*_a, **_k):
        yield pl.DataFrame(
            {
                "project_id": ["p1"],
                "issue_id": ["i1"],
                "value": [5.0],
                "slice_value": ["Story"],
                "calc_id": ["id-blocked_time_total"],
            }
        )

    monkeypatch.setattr(
        aging_extended, "iter_slicing_results", _fake_iter_slicing_aging
    )

    out = _asset_fn(aging_extended.calculate_aging_extended)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert out["status"] == "success"
    assert out["rows_written"] >= 2


def test_waste_slicing(monkeypatch):
    monkeypatch.setattr(waste, "get_definition_id", lambda *_a: "def-waste")
    monkeypatch.setattr(waste, "get_calculation_id", lambda *_a: "id-waste")
    monkeypatch.setattr(waste, "get_project_agg_id", lambda engine, pid: f"agg-{pid}")
    monkeypatch.setattr(waste, "write_fact_values", lambda df, *_a, **_k: df.height)

    def _read_table(_e, query, params=None):
        if "FROM clean_jira.issues" in query:
            return pl.DataFrame(
                {"id": ["i1"], "project_id": ["p1"], "type_name": ["Story"]}
            )
        if "FROM clean_jira.issue_statuses" in query:
            return pl.DataFrame({"id": ["s-c"], "name": ["Cancelled"]})
        if "FROM metrics.calculation_settings" in query:
            return pl.DataFrame(
                {
                    "id": [],
                    "project_id": [],
                    "settings_json": [],
                    "target_calculation_id": [],
                    "enabled": [],
                }
            )
        if "FROM clean_jira.issue_status_changelog" in query:
            return pl.DataFrame(
                {
                    "issue_id": [],
                    "from_status_id": [],
                    "to_status_id": [],
                    "changed_at": [],
                }
            )
        return pl.DataFrame()

    monkeypatch.setattr(waste, "read_table", _read_table)
    monkeypatch.setattr(
        waste.waste_logic,
        "calculate_cancellation_rate_weekly",
        lambda *_a: pl.DataFrame(
            {
                "project_id": ["p1"],
                "iso_week_start_date": [date(2026, 1, 5)],
                "cancellation_count": [1],
            }
        ),
    )

    monkeypatch.setattr(
        waste,
        "get_slice_rules",
        lambda *_a, **_k: pl.DataFrame(
            {"slice_rule_id": ["rule-1"], "enabled": [True]}
        ),
    )
    monkeypatch.setattr(
        waste,
        "apply_slicing",
        lambda *_a, **_k: pl.DataFrame(
            {
                "project_id": ["p1"],
                "time_id_src": [date(2026, 1, 5)],
                "value": [1],
                "slice_value": ["Story"],
            }
        ),
    )

    out = _asset_fn(waste.calculate_waste_metrics)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert out["status"] == "success"
    assert out["rows_written"] == 2
