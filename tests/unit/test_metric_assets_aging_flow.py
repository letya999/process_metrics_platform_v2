from datetime import datetime

import polars as pl

from pipelines.assets.metrics import aging, flow_efficiency


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


class _FakeResult:
    def __init__(self, mapping=None, scalar_value=None):
        self._mapping = mapping
        self._scalar = scalar_value

    def mappings(self):
        return self

    def first(self):
        return self._mapping

    def scalar(self):
        return self._scalar


class _FakeConn:
    def __init__(self, results):
        self._results = list(results)

    def execute(self, _query, params=None):
        return self._results.pop(0)


class _FakeConnCtx:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeEngine:
    def __init__(self, results):
        self._conn = _FakeConn(results)

    def connect(self):
        return _FakeConnCtx(self._conn)


def _asset_fn(defn):
    return defn.node_def.compute_fn.decorated_fn


def test_calculate_aging_success(monkeypatch):
    monkeypatch.setattr(
        aging, "get_definition_id", lambda *_args, **_kwargs: "def-aging"
    )
    monkeypatch.setattr(
        aging, "get_calculation_id", lambda *_args, **_kwargs: "calc-aging"
    )
    monkeypatch.setattr(aging, "get_project_agg_id", lambda *_args, **_kwargs: "agg-1")

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.issues i" in query:
            return pl.DataFrame(
                {
                    "id": ["i1"],
                    "project_id": ["p1"],
                    "key": ["P1-1"],
                    "type_name": ["Story"],
                    "status_id": ["s1"],
                    "jira_created_at": [datetime(2026, 1, 1)],
                }
            )
        if "FROM clean_jira.issue_status_changelog" in query:
            return pl.DataFrame(
                {
                    "issue_id": ["i1"],
                    "from_status_id": ["s0"],
                    "to_status_id": ["s1"],
                    "changed_at": [datetime(2026, 1, 2)],
                }
            )
        if "FROM clean_jira.boards" in query:
            return pl.DataFrame({"id": ["b1"], "project_id": ["p1"], "name": ["Board"]})
        if "FROM clean_jira.board_columns bc" in query:
            return pl.DataFrame(
                {
                    "id": ["c1"],
                    "board_id": ["b1"],
                    "name": ["In Progress"],
                    "position": [1],
                    "status_id": ["s1"],
                }
            )
        if "FROM clean_jira.issue_statuses" in query:
            return pl.DataFrame(
                {
                    "id": ["s1"],
                    "name": ["In Progress"],
                    "category": ["indeterminate"],
                }
            )
        if "metrics.fact_values" in query:
            return pl.DataFrame([[1]], schema=["count"])
        raise AssertionError(f"Unexpected query: {query}")

    monkeypatch.setattr(aging, "read_table", _read_table)
    monkeypatch.setattr(
        aging.aging_logic,
        "calculate_work_item_aging_facts",
        lambda **_kwargs: pl.DataFrame(
            {
                "issue_id": ["i1"],
                "project_id": ["p1"],
                "issue_key": ["P1-1"],
                "issue_type": ["Story"],
                "current_status": ["In Progress"],
                "commitment_start_at": [datetime(2026, 1, 2)],
                "age_days": [10.5],
                "age_in_status_days": [5.0],
            }
        ),
    )
    monkeypatch.setattr(
        aging, "get_slice_rules", lambda *_args, **_kwargs: pl.DataFrame()
    )
    monkeypatch.setattr(
        aging, "write_fact_values", lambda df, *_args, **_kwargs: df.height
    )

    out = _asset_fn(aging.calculate_aging)(_DummyContext(), _DummyDatabase(object()))
    assert out["status"] == "success"
    assert out["rows_written"] == 1


def test_calculate_flow_efficiency_success(monkeypatch):
    monkeypatch.setattr(
        flow_efficiency, "get_definition_id", lambda *_args, **_kwargs: "def-flow"
    )
    monkeypatch.setattr(
        flow_efficiency,
        "get_calculation_id",
        lambda _e, code: {
            "flow_active_days": "m1",
            "flow_wait_days": "m2",
            "flow_efficiency_pct": "m3",
        }[code],
    )
    monkeypatch.setattr(
        flow_efficiency, "get_project_agg_id", lambda *_args, **_kwargs: "agg-1"
    )

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.issues i" in query:
            return pl.DataFrame(
                {
                    "id": ["i1"],
                    "project_id": ["p1"],
                    "key": ["P1-1"],
                    "type_name": ["Story"],
                    "status_id": ["s1"],
                    "jira_created_at": [datetime(2026, 1, 1)],
                }
            )
        if "FROM clean_jira.issue_status_changelog" in query:
            return pl.DataFrame(
                {
                    "issue_id": ["i1"],
                    "from_status_id": ["s0"],
                    "to_status_id": ["s1"],
                    "changed_at": [datetime(2026, 1, 2)],
                }
            )
        if "FROM clean_jira.issue_statuses" in query:
            return pl.DataFrame(
                {
                    "id": ["s1", "s2", "s3"],
                    "name": ["In Progress", "To Do", "Done"],
                    "category": ["indeterminate", "todo", "done"],
                }
            )
        if "metrics.fact_values" in query:
            return pl.DataFrame([[1]], schema=["count"])
        raise AssertionError(f"Unexpected query: {query}")

    monkeypatch.setattr(flow_efficiency, "read_table", _read_table)
    monkeypatch.setattr(
        flow_efficiency.flow_logic,
        "calculate_flow_efficiency_per_issue",
        lambda **_kwargs: pl.DataFrame(
            {
                "issue_id": ["i1"],
                "project_id": ["p1"],
                "issue_key": ["P1-1"],
                "active_days": [2.0],
                "wait_days": [1.0],
                "efficiency_pct": [66.67],
                "completion_date": [datetime(2026, 1, 5)],
            }
        ),
    )
    monkeypatch.setattr(
        flow_efficiency, "get_slice_rules", lambda *_args, **_kwargs: pl.DataFrame()
    )
    monkeypatch.setattr(
        flow_efficiency, "write_fact_values", lambda df, *_args, **_kwargs: df.height
    )

    out = _asset_fn(flow_efficiency.calculate_flow_efficiency)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert out["status"] == "success"
    # 3 metrics per issue
    assert out["rows_written"] == 3


def test_calculate_aging_with_slices(monkeypatch):
    monkeypatch.setattr(
        aging, "get_definition_id", lambda *_args, **_kwargs: "def-aging"
    )
    monkeypatch.setattr(
        aging, "get_calculation_id", lambda *_args, **_kwargs: "calc-aging"
    )
    monkeypatch.setattr(aging, "get_project_agg_id", lambda *_args, **_kwargs: "agg-1")

    # Mocks for Base data
    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.issues i" in query:
            return pl.DataFrame(
                {
                    "id": ["i1"],
                    "project_id": ["p1"],
                    "key": ["P1-1"],
                    "type_name": ["Story"],
                    "status_id": ["s1"],
                    "jira_created_at": [datetime(2026, 1, 1)],
                }
            )
        if "FROM clean_jira.issue_status_changelog" in query:
            return pl.DataFrame(
                {
                    "issue_id": ["i1"],
                    "from_status_id": ["s0"],
                    "to_status_id": ["s1"],
                    "changed_at": [datetime(2026, 1, 2)],
                }
            )
        if "FROM clean_jira.boards" in query:
            return pl.DataFrame({"id": ["b1"], "project_id": ["p1"], "name": ["Board"]})
        if "FROM clean_jira.board_columns bc" in query:
            return pl.DataFrame(
                {
                    "id": ["c1"],
                    "board_id": ["b1"],
                    "name": ["In Progress"],
                    "position": [1],
                    "status_id": ["s1"],
                }
            )
        if "FROM clean_jira.issue_statuses" in query:
            return pl.DataFrame(
                {"id": ["s1"], "name": ["In Progress"], "category": ["indeterminate"]}
            )
        if "metrics.fact_values" in query:
            return pl.DataFrame([[1]], schema=["count"])
        return pl.DataFrame()

    monkeypatch.setattr(aging, "read_table", _read_table)

    # Base logic returns 1 row
    monkeypatch.setattr(
        aging.aging_logic,
        "calculate_work_item_aging_facts",
        lambda **_kwargs: pl.DataFrame(
            {
                "issue_id": ["i1"],
                "project_id": ["p1"],
                "issue_key": ["P1-1"],
                "issue_type": ["Story"],
                "current_status": ["In Progress"],
                "commitment_start_at": [datetime(2026, 1, 2)],
                "age_days": [10.5],
                "age_in_status_days": [5.0],
            }
        ),
    )

    # Rules: 1 rule
    monkeypatch.setattr(
        aging,
        "get_slice_rules",
        lambda *_args, **_kwargs: pl.DataFrame(
            {
                "slice_rule_id": ["r1"],
                "slice_rule_name": ["By Type"],
                "group_by_column": ["issue_type"],
                "enabled": [True],
            }
        ),
    )

    # apply_slicing returns 1 sliced row
    monkeypatch.setattr(
        aging,
        "apply_slicing",
        lambda *_args, **_kwargs: pl.DataFrame(
            {
                "issue_id": ["i1"],
                "project_id": ["p1"],
                "issue_key": ["P1-1"],
                "age_days": [10.5],
                "commitment_start_at": [datetime(2026, 1, 2)],
                "slice_value": ["Story"],
            }
        ),
    )

    monkeypatch.setattr(
        aging, "write_fact_values", lambda df, *_args, **_kwargs: df.height
    )

    out = _asset_fn(aging.calculate_aging)(_DummyContext(), _DummyDatabase(object()))
    assert out["status"] == "success"
    # 1 base + 1 sliced
    assert out["rows_written"] == 2
