import polars as pl

from pipelines.calculations import commitment_resolver


class _DummyResult:
    def __init__(self, val):
        self.val = val

    def fetchone(self):
        return self.val


class _DummyConn:
    def __init__(self, val=None):
        self.val = val

    def execute(self, statement, params=None):
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


def test_resolve_commitment_columns_returns_rule():
    engine = _DummyEngine(("rule-1", "col-1", "col-3", "In Progress", "Done"))
    result = commitment_resolver.resolve_commitment_columns(
        engine, "project-1", "board-1", "lead_time_days"
    )

    assert result is not None
    assert result["commitment_rule_id"] == "rule-1"
    assert result["start_column_id"] == "col-1"
    assert result["end_column_id"] == "col-3"


def test_resolve_commitment_columns_returns_none_when_missing():
    engine = _DummyEngine(None)
    result = commitment_resolver.resolve_commitment_columns(
        engine, "project-1", "board-1", "lead_time_days"
    )
    assert result is None


def test_identify_commitment_points_from_rule_happy_path():
    board_columns = pl.DataFrame(
        {
            "id": ["col-1", "col-2", "col-3"],
            "status_id": ["todo", "progress", "done"],
            "position": [1, 2, 3],
            "name": ["To Do", "In Progress", "Done"],
        }
    )
    rule = {
        "commitment_rule_id": "rule-1",
        "start_column_id": "col-1",
        "end_column_id": "col-3",
    }

    result = commitment_resolver.identify_commitment_points_from_rule(
        rule, board_columns
    )

    assert result["start_status_ids"] == ["todo"]
    assert result["end_status_ids"] == ["done"]
    assert sorted(result["middle_status_ids"]) == ["progress", "todo"]
    assert result["start_position"] == 1
    assert result["end_position"] == 3
    assert result["commitment_rule_id"] == "rule-1"


def test_identify_commitment_points_heuristic_empty_df():
    result = commitment_resolver.identify_commitment_points_heuristic(pl.DataFrame())
    assert result["start_status_ids"] == []
    assert result["end_status_ids"] == []
    assert result["middle_status_ids"] == []
    assert result["commitment_rule_id"] is None


def test_identify_commitment_points_heuristic_start_after_end_returns_empty():
    board_columns = pl.DataFrame(
        {
            "id": ["col-1", "col-2"],
            "status_id": ["done", "progress"],
            "position": [1, 2],
            "name": ["Done", "In Progress"],
        }
    )

    result = commitment_resolver.identify_commitment_points_heuristic(board_columns)
    assert result["start_status_ids"] == ["progress"]
    assert result["end_status_ids"] == ["done"]
    assert result["middle_status_ids"] == []


def test_identify_commitment_points_heuristic_happy_path():
    board_columns = pl.DataFrame(
        {
            "id": ["col-1", "col-2", "col-3"],
            "status_id": ["todo", "progress", "done"],
            "position": [1, 2, 3],
            "name": ["Backlog", "In Progress", "Done"],
        }
    )

    result = commitment_resolver.identify_commitment_points_heuristic(board_columns)
    assert result["start_status_ids"] == ["progress"]
    assert result["end_status_ids"] == ["done"]
    assert result["middle_status_ids"] == ["progress"]
    assert result["start_position"] == 2
    assert result["end_position"] == 3
