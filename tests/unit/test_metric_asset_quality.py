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


def test_quality_slice_calc_no_cross_project_rows(monkeypatch):
    """quality_slice_calc must not emit rows for projects absent from df_subset.

    Regression test for the bug where calculate_backflow_rate returns one row
    per sprint across ALL projects (filling 0.0 for unrelated projects).  When
    quality_slice_calc is called with issues from project P1 only, the returned
    DataFrame must contain rows for P1 sprints only — never for P2 sprints.
    """
    from datetime import timezone

    calc_ids = {"defect_density_by_type": "m1", "backflow_column_rate": "m2"}
    monkeypatch.setattr(quality, "get_definition_id", lambda *_a, **_k: "def-1")
    monkeypatch.setattr(quality, "get_calculation_id", lambda _e, c: calc_ids[c])
    monkeypatch.setattr(
        quality,
        "get_project_agg_id",
        lambda _e, pid: {"P1": "agg-1", "P2": "agg-2"}[pid],
    )
    monkeypatch.setattr(quality, "write_fact_values", lambda df, *_a, **_k: df.height)

    s1_start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    s2_start = datetime(2026, 1, 15, tzinfo=timezone.utc)
    s1_end = datetime(2026, 1, 14, tzinfo=timezone.utc)
    s2_end = datetime(2026, 1, 28, tzinfo=timezone.utc)

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.sprints" in query:
            return pl.DataFrame(
                {
                    "id": ["S1", "S2"],
                    "project_id": ["P1", "P2"],
                    "start_date": [s1_start, s2_start],
                    "end_date": [s1_end, s2_end],
                    "status": ["closed", "closed"],
                }
            )
        if "FROM clean_jira.sprint_issues" in query:
            return pl.DataFrame({"issue_id": ["I1", "I2"], "sprint_id": ["S1", "S2"]})
        if "FROM clean_jira.issues" in query:
            return pl.DataFrame(
                {
                    "id": ["I1", "I2"],
                    "project_id": ["P1", "P2"],
                    "issue_type_id": ["T1", "T1"],
                    "type_name": ["Bug", "Bug"],
                }
            )
        if "FROM clean_jira.issue_types" in query:
            return pl.DataFrame({"id": ["T1"], "name": ["Bug"]})
        if "FROM clean_jira.issue_status_changelog" in query:
            return pl.DataFrame(
                {
                    "issue_id": pl.Series([], dtype=pl.Utf8),
                    "from_status_id": pl.Series([], dtype=pl.Utf8),
                    "to_status_id": pl.Series([], dtype=pl.Utf8),
                    "changed_at": pl.Series([], dtype=pl.Datetime("us", "UTC")),
                }
            )
        if "FROM clean_jira.board_columns bc" in query:
            return pl.DataFrame(
                {
                    "id": ["C1"],
                    "board_id": ["B1"],
                    "name": ["To Do"],
                    "status_id": ["TODO"],
                    "position": [0],
                }
            )
        if "FROM metrics.calculation_settings" in query:
            return pl.DataFrame()
        raise AssertionError(query)

    monkeypatch.setattr(quality, "read_table", _read_table)
    monkeypatch.setattr(quality, "get_slice_rules", lambda *_a, **_k: pl.DataFrame())

    captured = {}

    def _write(df, engine, **kwargs):
        captured["df"] = df
        return df.height

    monkeypatch.setattr(quality, "write_fact_values", _write)

    _asset_fn(quality.calculate_quality_metrics)(
        _DummyContext(), _DummyDatabase(object())
    )

    # The base rows should have exactly one row per sprint (2 total, one per project)
    base_rows = captured["df"].filter(pl.col("slice_rule_id").is_null())
    p1_rows = base_rows.filter(pl.col("project_agg_id") == "agg-1")
    p2_rows = base_rows.filter(pl.col("project_agg_id") == "agg-2")
    assert p1_rows.height == 1, f"Expected 1 P1 base row, got {p1_rows.height}"
    assert p2_rows.height == 1, f"Expected 1 P2 base row, got {p2_rows.height}"


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
