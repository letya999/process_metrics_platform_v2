import uuid

import pandas as pd
import polars as pl

from pipelines.utils import polars_db


class _DummyConn:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params=None):
        self.calls.append((str(statement), params))

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


def test_write_fact_values_deletes_and_returns_zero_for_empty_df():
    engine = _DummyEngine()
    empty_df = pl.DataFrame(
        {
            "metric_id": [],
            "project_agg_id": [],
            "time_id": [],
            "value": [],
        }
    )

    inserted = polars_db.write_fact_values(
        df=empty_df,
        engine=engine,
        metric_ids=["m1"],
        project_agg_ids=["p1"],
        time_id_start=20260101,
        time_id_end=20260131,
    )

    assert inserted == 0
    assert len(engine.conn.calls) == 1
    _, params = engine.conn.calls[0]
    assert params == {
        "metric_ids": ["m1"],
        "project_agg_ids": ["p1"],
        "start": 20260101,
        "end": 20260131,
    }


def test_write_fact_values_uses_adbc_path(monkeypatch):
    engine = _DummyEngine()
    df = pl.DataFrame(
        {
            "metric_id": ["m1"],
            "project_agg_id": ["p1"],
            "time_id": [20260101],
            "value": [1.0],
        }
    )
    called = {}

    def _fake_write_database(self, table_name, connection, if_table_exists, engine):
        called["table_name"] = table_name
        called["connection"] = connection
        called["if_table_exists"] = if_table_exists
        called["engine"] = engine

    monkeypatch.setattr(pl.DataFrame, "write_database", _fake_write_database)

    inserted = polars_db.write_fact_values(
        df=df,
        engine=engine,
        metric_ids=["m1"],
        project_agg_ids=["p1"],
        time_id_start=20260101,
        time_id_end=20260101,
    )

    assert inserted == 1
    assert called["table_name"] == "metrics.fact_values"
    assert called["if_table_exists"] == "append"
    assert called["engine"] == "adbc"


def test_write_fact_values_falls_back_to_pandas(monkeypatch):
    engine = _DummyEngine()
    df = pl.DataFrame(
        {
            "metric_id": ["m1"],
            "project_agg_id": ["p1"],
            "time_id": [20260101],
            "value": [1.0],
        }
    )

    def _failing_write_database(self, table_name, connection, if_table_exists, engine):
        raise RuntimeError("adbc failed")

    to_sql_calls = {"count": 0}

    def _fake_to_sql(self, name, con, schema, if_exists, index, method, chunksize=None):
        to_sql_calls["count"] += 1
        assert name == "fact_values"
        assert schema == "metrics"
        assert if_exists == "append"
        assert method == "multi"
        assert chunksize == 5000

    monkeypatch.setattr(pl.DataFrame, "write_database", _failing_write_database)
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
    assert to_sql_calls["count"] == 1


def test_write_table_replace_truncates_and_appends(monkeypatch):
    engine = _DummyEngine()
    df = pl.DataFrame(
        {"id": [None], "value": [1.0], "created_at": [None], "updated_at": [None]}
    )

    to_sql_calls = {"count": 0}

    def _fake_to_sql(self, name, con, schema, if_exists, index, method):
        to_sql_calls["count"] += 1
        assert name == "fact_values"
        assert schema == "metrics"
        assert if_exists == "append"
        assert index is False
        assert method == "multi"

    monkeypatch.setattr(pd.DataFrame, "to_sql", _fake_to_sql)

    polars_db.write_table(
        df, engine, table="fact_values", schema="metrics", if_exists="replace"
    )

    assert to_sql_calls["count"] == 1
    assert len(engine.conn.calls) == 1
    assert "TRUNCATE TABLE metrics.fact_values" in engine.conn.calls[0][0]


def test_execute_sql_runs_statement():
    engine = _DummyEngine()
    polars_db.execute_sql(engine, "SELECT 1")
    assert len(engine.conn.calls) == 1
