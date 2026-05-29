from unittest.mock import MagicMock

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


def test_read_table_with_params_uses_polars_read_database(monkeypatch):
    captured = {}

    def _fake_read_database(query, connection, execute_options=None):
        captured["execute_options"] = execute_options
        return pl.DataFrame({"id": ["abc"], "name": ["row"]})

    monkeypatch.setattr(pl, "read_database", _fake_read_database)

    engine = _DummyEngine()
    result = polars_db.read_table(
        engine, "SELECT * FROM t WHERE id=:id", params={"id": "123"}
    )

    assert result["id"][0] == "abc"
    assert result["name"][0] == "row"
    assert captured["execute_options"] == {"parameters": {"id": "123"}}


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


def test_write_fact_values_atomic_flow():
    engine = _DummyEngine()
    df = pl.DataFrame(
        {
            "metric_id": ["m1"],
            "project_agg_id": ["p1"],
            "time_id": [20260101],
            "value": [1.0],
        }
    )

    inserted = polars_db.write_fact_values(
        df=df,
        engine=engine,
        metric_ids=["m1"],
        project_agg_ids=["p1"],
        time_id_start=20260101,
        time_id_end=20260101,
    )

    assert inserted == 1

    # Check SQL calls sequence (dict-based insert, no pandas to_sql)
    calls = [c[0] for c in engine.conn.calls]
    assert any("CREATE TEMP TABLE _fact_values_stage" in c for c in calls)
    assert any("DELETE FROM metrics.fact_values" in c for c in calls)
    assert any("INSERT INTO metrics.fact_values" in c for c in calls)
    assert any("DROP TABLE _fact_values_stage" in c for c in calls)


def test_execute_sql_runs_statement():
    engine = _DummyEngine()
    polars_db.execute_sql(engine, "SELECT 1")
    assert len(engine.conn.calls) == 1


# ---------------------------------------------------------------------------
# write_fact_values slice_rule_id scoping (the base-vs-sliced DELETE bug fix)
# ---------------------------------------------------------------------------

_BASE_COLS = {
    "metric_id": ["m1"],
    "project_agg_id": ["p1"],
    "time_id": [20260301],
    "value": [1.0],
}


def _delete_sql(engine: _DummyEngine) -> str:
    """Return the DELETE statement that was executed."""
    stmts = [c[0] for c in engine.conn.calls]
    return next(s for s in stmts if "DELETE FROM metrics.fact_values" in s)


def _delete_params(engine: _DummyEngine) -> dict:
    """Return the params dict for the DELETE statement."""
    for stmt, params in engine.conn.calls:
        if "DELETE FROM metrics.fact_values" in stmt:
            return params or {}
    return {}


def test_write_fact_values_base_delete_scopes_to_null_slice():
    """Base write (no slice_rule_id column) must scope DELETE to IS NULL rows only."""
    engine = _DummyEngine()
    df = pl.DataFrame(_BASE_COLS)

    polars_db.write_fact_values(
        df=df,
        engine=engine,
        metric_ids=["m1"],
        project_agg_ids=["p1"],
        time_id_start=20260301,
        time_id_end=20260301,
    )

    sql = _delete_sql(engine)
    assert "slice_rule_id IS NULL" in sql
    assert "ANY(CAST(:slice_rule_ids" not in sql


def test_write_fact_values_base_with_null_column_scopes_to_null():
    """Base write with explicit slice_rule_id=None must scope DELETE to IS NULL."""
    engine = _DummyEngine()
    df = pl.DataFrame({**_BASE_COLS, "slice_rule_id": [None]})

    polars_db.write_fact_values(
        df=df,
        engine=engine,
        metric_ids=["m1"],
        project_agg_ids=["p1"],
        time_id_start=20260301,
        time_id_end=20260301,
    )

    sql = _delete_sql(engine)
    assert "slice_rule_id IS NULL" in sql


def test_write_fact_values_sliced_delete_scopes_to_rule_id():
    """Sliced write must scope DELETE to that specific slice_rule_id only."""
    rule_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    engine = _DummyEngine()
    df = pl.DataFrame({**_BASE_COLS, "slice_rule_id": [rule_id]})

    polars_db.write_fact_values(
        df=df,
        engine=engine,
        metric_ids=["m1"],
        project_agg_ids=["p1"],
        time_id_start=20260301,
        time_id_end=20260301,
    )

    sql = _delete_sql(engine)
    params = _delete_params(engine)
    assert "slice_rule_ids" in sql
    assert rule_id in params.get("slice_rule_ids", [])
    assert "IS NULL" not in sql


def test_write_fact_values_sliced_does_not_affect_base_in_same_range():
    """Key regression: sliced DELETE must NOT contain IS NULL — base rows are safe."""
    rule_id = "11111111-2222-3333-4444-555555555555"
    engine = _DummyEngine()
    df = pl.DataFrame({**_BASE_COLS, "slice_rule_id": [rule_id]})

    polars_db.write_fact_values(
        df=df,
        engine=engine,
        metric_ids=["m1"],
        project_agg_ids=["p1"],
        time_id_start=20260301,
        time_id_end=20260301,
    )

    sql = _delete_sql(engine)
    # The DELETE must restrict to this rule_id, not wipe all rows
    assert "slice_rule_id = ANY" in sql or "slice_rule_ids" in sql
    assert "slice_rule_id IS NULL" not in sql


def test_write_fact_values_mixed_slice_uses_full_delete():
    """Mixed batch (null + non-null slice_rule_id) falls back to full delete."""
    rule_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    engine = _DummyEngine()
    df = pl.DataFrame(
        {
            "metric_id": ["m1", "m1"],
            "project_agg_id": ["p1", "p1"],
            "time_id": [20260301, 20260302],
            "value": [1.0, 2.0],
            "slice_rule_id": [None, rule_id],
        }
    )

    polars_db.write_fact_values(
        df=df,
        engine=engine,
        metric_ids=["m1"],
        project_agg_ids=["p1"],
        time_id_start=20260301,
        time_id_end=20260302,
    )

    sql = _delete_sql(engine)
    # Full delete — no scoping
    assert "slice_rule_id" not in sql
