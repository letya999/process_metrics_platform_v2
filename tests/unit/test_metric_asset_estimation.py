from unittest.mock import MagicMock

import polars as pl
import pytest

from pipelines.assets.metrics import estimation


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
    monkeypatch.setattr(estimation, "get_definition_id", lambda *_a, **_k: "def-e")
    monkeypatch.setattr(estimation, "get_calculation_id", lambda *_a, **_k: "metric")


def test_calculate_estimation_metrics_skipped(monkeypatch):
    monkeypatch.setattr(estimation, "read_table", lambda *_a, **_k: pl.DataFrame())
    out = _asset_fn(estimation.calculate_estimation_metrics)(
        _DummyContext(), _DummyDatabase(MagicMock())
    )
    assert out["status"] == "skipped"


def test_calculate_estimation_metrics_skips_without_story_points_field(monkeypatch):
    monkeypatch.setattr(estimation, "get_project_agg_id", lambda *_a, **_k: "agg-p1")
    monkeypatch.setattr(estimation, "get_calculation_id", lambda *_a, **_k: "m_vol")

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.issues" in query:
            return pl.DataFrame(
                {
                    "id": ["I1"],
                    "project_id": ["P1"],
                    "issue_key": ["P1-1"],
                    "type_name": ["Task"],
                }
            )
        if "FROM clean_jira.field_keys" in query:
            return pl.DataFrame(
                {"id": ["F1"], "external_key": ["priority"], "name": ["Priority"]}
            )
        if "FROM clean_jira.field_values" in query:
            return pl.DataFrame(
                {"issue_id": [], "field_key_id": [], "json_value": []},
                schema={
                    "issue_id": pl.String,
                    "field_key_id": pl.String,
                    "json_value": pl.String,
                },
            )
        if "FROM clean_jira.field_value_changelog" in query:
            return pl.DataFrame(
                {
                    "issue_id": [],
                    "field_key_id": [],
                    "old_value": [],
                    "new_value": [],
                    "change_time": [],
                },
                schema={
                    "issue_id": pl.String,
                    "field_key_id": pl.String,
                    "old_value": pl.String,
                    "new_value": pl.String,
                    "change_time": pl.String,
                },
            )

        raise AssertionError(query)

    monkeypatch.setattr(estimation, "read_table", _read_table)
    monkeypatch.setattr(estimation, "resolve_unit_field", lambda *_a, **_k: None)
    out = _asset_fn(estimation.calculate_estimation_metrics)(
        _DummyContext(), _DummyDatabase(MagicMock())
    )
    assert out["status"] == "skipped"
    assert out["reason"] == "No Story Points field found"


def test_calculate_estimation_metrics_success(monkeypatch):
    monkeypatch.setattr(estimation, "get_project_agg_id", lambda *_a, **_k: "agg-p1")
    monkeypatch.setattr(estimation, "get_calculation_id", lambda *_a, **_k: "m_vol")
    monkeypatch.setattr(
        estimation, "write_fact_values", lambda df, *_a, **_k: df.height
    )
    monkeypatch.setattr(
        estimation.estimation_logic,
        "calculate_estimate_volatility",
        lambda *_a, **_k: pl.DataFrame(
            {"project_id": ["P1"], "issue_id": ["I1"], "volatility": [3.0]}
        ),
    )

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.issues" in query:
            return pl.DataFrame(
                {
                    "id": ["I1"],
                    "project_id": ["P1"],
                    "issue_key": ["P1-1"],
                    "type_name": ["Task"],
                }
            )
        if "FROM clean_jira.field_keys" in query:
            return pl.DataFrame(
                {
                    "id": ["SP"],
                    "external_key": ["customfield_10036"],
                    "name": ["Story Points"],
                }
            )
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
                    "change_time": ["2026-01-02"],
                }
            )
        raise AssertionError(query)

    monkeypatch.setattr(estimation, "read_table", _read_table)
    monkeypatch.setattr(
        estimation,
        "resolve_unit_field",
        lambda *_a, **_k: {
            "source_field_id": "SP",
            "source_entity": "clean_jira.field_keys",
        },
    )
    out = _asset_fn(estimation.calculate_estimation_metrics)(
        _DummyContext(), _DummyDatabase(MagicMock())
    )
    assert out["status"] == "success"
    assert out["rows_written"] == 1


def test_estimation_data_quality_check_fail_and_pass(monkeypatch):
    monkeypatch.setattr(estimation, "get_calculation_id", lambda *_a, **_k: "m_vol")
    monkeypatch.setattr(
        estimation, "read_table", lambda *_a, **_k: pl.DataFrame({"cnt": [2]})
    )
    failed = _asset_fn(estimation.estimation_data_quality_check)(
        _DummyDatabase(MagicMock())
    )
    assert failed.passed is False

    monkeypatch.setattr(
        estimation, "read_table", lambda *_a, **_k: pl.DataFrame({"cnt": [0]})
    )
    passed = _asset_fn(estimation.estimation_data_quality_check)(
        _DummyDatabase(MagicMock())
    )
    assert passed.passed is True
