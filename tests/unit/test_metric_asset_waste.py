from datetime import datetime

import polars as pl

from pipelines.assets.metrics import waste


class _DummyDatabase:
    def __init__(self, engine):
        self._engine = engine

    def get_engine(self):
        return self._engine


def _asset_fn(defn):
    return defn.node_def.compute_fn.decorated_fn


def test_calculate_waste_metrics_skipped(monkeypatch):
    monkeypatch.setattr(waste, "read_table", lambda *_a, **_k: pl.DataFrame())
    out = _asset_fn(waste.calculate_waste_metrics)(None, _DummyDatabase(object()))
    assert out["status"] == "skipped"


def test_calculate_waste_metrics_no_data(monkeypatch):
    monkeypatch.setattr(waste, "get_calculation_id", lambda *_a, **_k: "m1")
    monkeypatch.setattr(waste, "get_project_agg_id", lambda *_a, **_k: "agg-1")

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.issues" in query:
            return pl.DataFrame({"id": ["I1"], "project_id": ["P1"]})
        if "FROM clean_jira.issue_status_changelog" in query:
            return pl.DataFrame({"issue_id": [], "to_status_id": [], "changed_at": []})
        if "FROM clean_jira.issue_statuses" in query:
            return pl.DataFrame({"id": ["S1"], "name": ["In Progress"]})
        if "FROM metrics.calculation_settings" in query:
            return pl.DataFrame(
                schema={"project_id": pl.Utf8, "settings_json": pl.Object}
            )
        raise AssertionError(query)

    monkeypatch.setattr(waste, "read_table", _read_table)
    monkeypatch.setattr(
        waste.waste_logic,
        "calculate_cancellation_rate_weekly",
        lambda *_a, **_k: pl.DataFrame(),
    )

    out = _asset_fn(waste.calculate_waste_metrics)(None, _DummyDatabase(object()))
    assert out["status"] == "no_data"


def test_calculate_waste_metrics_success(monkeypatch):
    monkeypatch.setattr(waste, "get_calculation_id", lambda *_a, **_k: "m1")
    monkeypatch.setattr(waste, "get_project_agg_id", lambda *_a, **_k: "agg-1")
    monkeypatch.setattr(waste, "write_fact_values", lambda df, *_a, **_k: df.height)

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.issues" in query:
            return pl.DataFrame({"id": ["I1"], "project_id": ["P1"]})
        if "FROM clean_jira.issue_status_changelog" in query:
            return pl.DataFrame(
                {
                    "issue_id": ["I1"],
                    "to_status_id": ["CANCELLED"],
                    "changed_at": [datetime(2026, 1, 2)],
                }
            )
        if "FROM clean_jira.issue_statuses" in query:
            return pl.DataFrame({"id": ["CANCELLED"], "name": ["Cancelled"]})
        if "FROM metrics.calculation_settings" in query:
            return pl.DataFrame(
                {
                    "project_id": [None],
                    "settings_json": [{"cancelled_status_ids": ["CANCELLED"]}],
                }
            )
        raise AssertionError(query)

    monkeypatch.setattr(waste, "read_table", _read_table)
    monkeypatch.setattr(
        waste.waste_logic,
        "calculate_cancellation_rate_weekly",
        lambda *_a, **_k: pl.DataFrame(
            {
                "project_id": ["P1"],
                "iso_week_start_date": [datetime(2025, 12, 30)],
                "cancellation_count": [1],
            }
        ),
    )

    out = _asset_fn(waste.calculate_waste_metrics)(None, _DummyDatabase(object()))
    assert out["status"] == "success"
    assert out["rows_written"] == 1


def test_waste_data_quality_check_fail_and_pass(monkeypatch):
    monkeypatch.setattr(waste, "get_calculation_id", lambda *_a, **_k: "m1")
    monkeypatch.setattr(
        waste, "read_table", lambda *_a, **_k: pl.DataFrame({"cnt": [1]})
    )
    failed = _asset_fn(waste.waste_data_quality_check)(_DummyDatabase(object()))
    assert failed.passed is False

    monkeypatch.setattr(
        waste, "read_table", lambda *_a, **_k: pl.DataFrame({"cnt": [0]})
    )
    passed = _asset_fn(waste.waste_data_quality_check)(_DummyDatabase(object()))
    assert passed.passed is True
