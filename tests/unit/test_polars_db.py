import uuid
from unittest.mock import MagicMock

import pandas as pd
import polars as pl
import pytest

from pipelines.utils import polars_db


class _DummyConn:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params=None):
        self.calls.append((str(statement), params))
        # Mock successful execution
        return MagicMock()

    def commit(self):
        return None


class _DummyCtx:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, exc_type, exc, tb):
        return False


class _DummyEngine:
    def __init__(self, url="postgresql://localhost/test"):
        self.url = url
        self.conn = _DummyConn()

    def begin(self):
        return _DummyCtx(self.conn)

    def connect(self):
        return _DummyCtx(self.conn)


def test_read_table_without_params_uses_polars_uri(monkeypatch):
    captured = {}

    def _fake_read_database_uri(uri, query):
        captured["uri"] = uri
        captured["query"] = query
        return pl.DataFrame({"x": [1]})

    monkeypatch.setattr(pl, "read_database_uri", _fake_read_database_uri)

    engine = _DummyEngine(url="postgresql://localhost/db1")
    result = polars_db.read_table(engine, "SELECT 1")

    assert result["x"][0] == 1
    assert captured["uri"] == "postgresql://localhost/db1"
    assert captured["query"] == "SELECT 1"


def test_read_table_with_params_uses_pandas_and_casts_uuid(monkeypatch):
    uid = uuid.uuid4()

    def _fake_read_sql(_query, _engine, params=None):
        assert params == {"id": "123"}
        return pd.DataFrame({"id": [uid], "name": ["row"]})

    monkeypatch.setattr(pd, "read_sql", _fake_read_sql)

    engine = _DummyEngine()
    result = polars_db.read_table(
        engine, "SELECT * FROM t WHERE id=:id", params={"id": "123"}
    )

    assert result["id"][0] == str(uid)
    assert result["name"][0] == "row"


def test_write_fact_values_validates_schema():
    engine = _DummyEngine()
    invalid_df = pl.DataFrame({"wrong": [1]})

    with pytest.raises(ValueError, match="missing required fact_values columns"):
        polars_db.write_fact_values(
            df=invalid_df,
            engine=engine,
            metric_ids=["m1"],
            project_agg_ids=["p1"],
            time_id_start=20260101,
            time_id_end=20260131,
        )


def test_write_fact_values_atomic_flow(monkeypatch):
    engine = _DummyEngine()
    df = pl.DataFrame(
        {
            "metric_id": ["m1"],
            "project_agg_id": ["p1"],
            "time_id": [20260101],
            "value": [1.0],
        }
    )

    to_sql_called = []

    def _fake_to_sql(self, name, con, if_exists, index, method, chunksize=None):
        to_sql_called.append(name)
        assert name == "_fact_values_stage"
        assert if_exists == "append"

    monkeypatch.setattr(pd.DataFrame, "to_sql", _fake_to_sql)

    inserted = polars_db.write_fact_values(
        df=df,
        engine=engine,
        metric_ids=["m1"],
        project_agg_ids=["p1"],
        time_id_start=20260101,
        time_id_end=20260101,
    )

    assert inserted == 1
    assert "_fact_values_stage" in to_sql_called

    # Check SQL calls sequence
    calls = [c[0] for c in engine.conn.calls]
    assert any("CREATE TEMP TABLE _fact_values_stage" in c for c in calls)
    assert any("DELETE FROM metrics.fact_values" in c for c in calls)
    assert any("INSERT INTO metrics.fact_values" in c for c in calls)
    assert any("DROP TABLE _fact_values_stage" in c for c in calls)


def test_execute_sql_runs_statement():
    engine = _DummyEngine()
    polars_db.execute_sql(engine, "SELECT 1")
    assert len(engine.conn.calls) == 1
