from datetime import datetime

import polars as pl

from pipelines.assets.metrics import quality


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
    return defn.node_def.compute_fn.decorated_fn


def test_calculate_quality_metrics_skipped(monkeypatch):
    monkeypatch.setattr(quality, "get_definition_id", lambda *_a, **_k: "def-1")
    monkeypatch.setattr(quality, "get_calculation_id", lambda *_a, **_k: "calc-1")
    monkeypatch.setattr(quality, "read_table", lambda *_a, **_k: pl.DataFrame())
    out = _asset_fn(quality.calculate_quality_metrics)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert out["status"] == "skipped"


def test_calculate_quality_metrics_no_data(monkeypatch):
    calc_ids = {"defect_density_by_type": "m1", "backflow_column_rate": "m2"}
    monkeypatch.setattr(quality, "get_definition_id", lambda *_a, **_k: "def-1")
    monkeypatch.setattr(quality, "get_calculation_id", lambda _e, c: calc_ids[c])
    monkeypatch.setattr(quality, "get_project_agg_id", lambda *_a, **_k: "agg-1")

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.sprints" in query:
            return pl.DataFrame(
                {
                    "id": ["S1"],
                    "project_id": ["P1"],
                    "start_date": [datetime(2026, 1, 1)],
                }
            )
        if "FROM clean_jira.sprint_issues" in query:
            return pl.DataFrame({"issue_id": ["I1"], "sprint_id": ["S1"]})
        if "FROM clean_jira.issues" in query:
            return pl.DataFrame(
                {
                    "id": ["I1"],
                    "project_id": ["P1"],
                    "issue_type_id": ["T1"],
                    "type_name": ["Story"],
                }
            )
        if "FROM clean_jira.issue_types" in query:
            return pl.DataFrame({"id": ["T1"], "name": ["Story"]})
        if "FROM clean_jira.issue_status_changelog" in query:
            return pl.DataFrame(
                {
                    "issue_id": [],
                    "from_status_id": [],
                    "to_status_id": [],
                    "changed_at": [],
                }
            )
        if "FROM clean_jira.board_columns bc" in query:
            return pl.DataFrame(
                {
                    "id": ["C1"],
                    "board_id": ["B1"],
                    "name": ["To Do"],
                    "status_id": ["TODO"],
                    "position": [1],
                }
            )
        if "FROM metrics.calculation_settings" in query:
            return pl.DataFrame()
        raise AssertionError(query)

    monkeypatch.setattr(quality, "read_table", _read_table)
    monkeypatch.setattr(
        quality.quality_logic,
        "calculate_backflow_rate",
        lambda *_a, **_k: pl.DataFrame(),
    )
    monkeypatch.setattr(quality, "get_slice_rules", lambda *_a, **_k: pl.DataFrame())

    out = _asset_fn(quality.calculate_quality_metrics)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert out["status"] == "no_data"


def test_calculate_quality_metrics_success_with_slicing(monkeypatch):
    calc_ids = {"defect_density_by_type": "m1", "backflow_column_rate": "m2"}
    monkeypatch.setattr(quality, "get_definition_id", lambda *_a, **_k: "def-1")
    monkeypatch.setattr(quality, "get_calculation_id", lambda _e, c: calc_ids[c])
    monkeypatch.setattr(quality, "get_project_agg_id", lambda *_a, **_k: "agg-1")
    monkeypatch.setattr(quality, "write_fact_values", lambda df, *_a, **_k: df.height)

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.sprints" in query:
            return pl.DataFrame(
                {
                    "id": ["S1"],
                    "project_id": ["P1"],
                    "start_date": [datetime(2026, 1, 1)],
                }
            )
        if "FROM clean_jira.sprint_issues" in query:
            return pl.DataFrame({"issue_id": ["I1"], "sprint_id": ["S1"]})
        if "FROM clean_jira.issues" in query:
            return pl.DataFrame(
                {
                    "id": ["I1"],
                    "project_id": ["P1"],
                    "issue_type_id": ["T1"],
                    "type_name": ["Story"],
                }
            )
        if "FROM clean_jira.issue_types" in query:
            return pl.DataFrame({"id": ["T1"], "name": ["Story"]})
        if "FROM clean_jira.issue_status_changelog" in query:
            return pl.DataFrame(
                {
                    "issue_id": ["I1"],
                    "from_status_id": ["INPROG"],
                    "to_status_id": ["TODO"],
                    "changed_at": [datetime(2026, 1, 2)],
                }
            )
        if "FROM clean_jira.board_columns bc" in query:
            return pl.DataFrame(
                {
                    "id": ["C1"],
                    "board_id": ["B1"],
                    "name": ["To Do"],
                    "status_id": ["TODO"],
                    "position": [1],
                }
            )
        if "FROM metrics.calculation_settings" in query:
            return pl.DataFrame(
                {
                    "id": ["set1"],
                    "project_id": [None],
                    "settings_json": [
                        {"numerator_type": "Bug", "denominator_type": "Story"}
                    ],
                }
            )
        raise AssertionError(query)

    monkeypatch.setattr(quality, "read_table", _read_table)
    monkeypatch.setattr(
        quality.quality_logic,
        "calculate_defect_density",
        lambda *_a, **_k: pl.DataFrame(
            {
                "project_id": ["P1"],
                "start_date": [datetime(2026, 1, 1)],
                "density_ratio": [0.5],
                "iteration_id": ["S1"],
            }
        ),
    )
    monkeypatch.setattr(
        quality.quality_logic,
        "calculate_backflow_rate",
        lambda *_a, **_k: pl.DataFrame(
            {
                "project_id": ["P1"],
                "start_date": [datetime(2026, 1, 1)],
                "backflow_pct": [25.0],
                "iteration_id": ["S1"],
            }
        ),
    )
    monkeypatch.setattr(
        quality,
        "get_slice_rules",
        lambda *_a, **_k: pl.DataFrame(
            {
                "slice_rule_id": ["rule-1"],
                "slice_rule_name": ["By Type"],
                "group_by_column": ["issue_type"],
                "source_table": ["clean_jira.issues"],
                "project_id": [None],
                "enabled": [True],
            }
        ),
    )
    monkeypatch.setattr(
        quality,
        "apply_slicing",
        lambda *_a, **_k: pl.DataFrame(
            {
                "project_id": ["P1"],
                "start_date": [datetime(2026, 1, 1)],
                "value": [0.3],
                "iteration_id": ["S1"],
                "slice_value": ["Story"],
                "calc_id": ["m1"],
                "settings_id": [None],
            }
        ),
    )

    out = _asset_fn(quality.calculate_quality_metrics)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert out["status"] == "success"
    assert out["rows_written"] == 3


def test_quality_data_quality_check_fail_and_pass(monkeypatch):
    monkeypatch.setattr(quality, "get_calculation_id", lambda *_a, **_k: "m2")
    monkeypatch.setattr(
        quality, "read_table", lambda *_a, **_k: pl.DataFrame({"cnt": [1]})
    )
    failed = _asset_fn(quality.quality_data_quality_check)(_DummyDatabase(object()))
    assert failed.passed is False
    monkeypatch.setattr(
        quality, "read_table", lambda *_a, **_k: pl.DataFrame({"cnt": [0]})
    )
    passed = _asset_fn(quality.quality_data_quality_check)(_DummyDatabase(object()))
    assert passed.passed is True
