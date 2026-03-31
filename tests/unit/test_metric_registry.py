import pytest

from pipelines.utils import metric_registry


@pytest.fixture(autouse=True)
def clear_registry_cache():
    metric_registry.clear_cache()


class _DummyResult:
    def __init__(self, val):
        self.val = val

    def scalar(self):
        return self.val

    def fetchone(self):
        if self.val is None:
            return None
        return (self.val, "mock_entity")

    def fetchall(self):
        if self.val is None:
            return []
        return [(self.val, "mock_entity")]


class _DummyConn:
    def __init__(self, val=None):
        self.calls = []
        self.val = val

    def execute(self, statement, params=None):
        self.calls.append((str(statement), params))
        return _DummyResult(self.val)


class _DummyBeginCtx:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, exc_type, exc, tb):
        return False


class _DummyEngine:
    def __init__(self, val=None):
        self.conn = _DummyConn(val)

    def connect(self):
        return _DummyBeginCtx(self.conn)

    def begin(self):
        return _DummyBeginCtx(self.conn)


def test_get_calculation_id_uses_cache():
    engine = _DummyEngine("calc-uuid-1")
    first = metric_registry.get_calculation_id(engine, "lead_time_days")
    second = metric_registry.get_calculation_id(engine, "lead_time_days")

    assert first == "calc-uuid-1"
    assert second == "calc-uuid-1"
    assert len(engine.conn.calls) == 1


def test_get_calculation_id_raises_on_missing():
    engine = _DummyEngine(None)
    with pytest.raises(ValueError, match="not found"):
        metric_registry.get_calculation_id(engine, "missing_calc")


def test_get_definition_id_raises_on_missing():
    engine = _DummyEngine(None)
    with pytest.raises(ValueError, match="not found"):
        metric_registry.get_definition_id(engine, "missing_metric")


def test_get_project_agg_id_existing_row():
    engine = _DummyEngine("agg-1")
    result = metric_registry.get_project_agg_id(engine, "proj-1")
    assert result == "agg-1"


def test_get_project_agg_id_raises_when_project_not_found():
    engine = _DummyEngine(None)
    with pytest.raises(ValueError, match="not found"):
        metric_registry.get_project_agg_id(engine, "proj-404")


def test_get_project_agg_id_attempts_sync_before_raising():
    engine = _DummyEngine(None)
    with pytest.raises(ValueError, match="not found"):
        metric_registry.get_project_agg_id(engine, "proj-404")

    assert any(
        "INSERT INTO metrics.dim_projects" in call[0] for call in engine.conn.calls
    )


def test_resolve_unit_field_returns_project_specific_or_none():
    engine1 = _DummyEngine("field-1")
    result = metric_registry.resolve_unit_field(engine1, "project-1", "story_points")
    assert result == {"source_field_id": "field-1", "source_entity": "mock_entity"}

    engine2 = _DummyEngine(None)
    assert (
        metric_registry.resolve_unit_field(engine2, "project-1", "story_points") is None
    )
