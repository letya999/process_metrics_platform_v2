from datetime import date, datetime

import polars as pl

from pipelines.assets.metrics import (
    backlog_growth,
    cumulative_flow,
    lead_time,
    refresh,
    throughput,
    time_to_market,
    velocity,
)


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

    def execute(self, _query):
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


def test_calculate_velocity_success(monkeypatch):
    monkeypatch.setattr(
        velocity, "get_definition_id", lambda *_args, **_kwargs: "def-v"
    )
    monkeypatch.setattr(
        velocity,
        "get_calculation_id",
        lambda _e, c: {
            "velocity_planned_sp": "m1",
            "velocity_completed_sp": "m2",
            "velocity_planned_count": "m3",
            "velocity_completed_count": "m4",
        }[c],
    )
    monkeypatch.setattr(
        velocity, "get_project_agg_id", lambda *_args, **_kwargs: "agg-1"
    )

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.sprints" in query:
            return pl.DataFrame(
                {
                    "id": ["sp-1"],
                    "project_id": ["p1"],
                    "name": ["Sprint 1"],
                    "start_date": [date(2026, 1, 1)],
                    "end_date": [date(2026, 1, 7)],
                    "complete_date": [date(2026, 1, 7)],
                    "project_key": ["P1"],
                }
            )
        if "FROM clean_jira.sprint_issues si" in query:
            return pl.DataFrame({"issue_id": ["i1"], "sprint_id": ["sp-1"]})
        if "FROM clean_jira.sprint_issues_changelog" in query:
            return pl.DataFrame(
                {"issue_id": [], "sprint_id": [], "action": [], "changed_at": []}
            )
        if "FROM clean_jira.issues i" in query:
            return pl.DataFrame(
                {
                    "id": ["i1"],
                    "project_id": ["p1"],
                    "key": ["P1-1"],
                    "type_name": ["Story"],
                    "status_id": ["s1"],
                    "jira_created_at": [datetime(2026, 1, 1)],
                    "jira_resolved_at": [datetime(2026, 1, 7)],
                }
            )
        if "FROM clean_jira.field_keys" in query:
            return pl.DataFrame({"id": ["fk"], "external_key": ["sp"], "name": ["SP"]})
        if "FROM clean_jira.field_values" in query:
            return pl.DataFrame(
                {"issue_id": ["i1"], "field_key_id": ["fk"], "json_value": ["3"]}
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
                    "name": ["Done"],
                    "status_id": ["s1"],
                    "position": [1],
                }
            )
        if "FROM clean_jira.field_value_changelog" in query:
            return pl.DataFrame(
                {
                    "issue_id": [],
                    "field_key_id": [],
                    "old_value": [],
                    "new_value": [],
                    "changed_at": [],
                }
            )
        if "FROM clean_jira.issue_statuses" in query:
            return pl.DataFrame({"id": ["s1"], "name": ["Done"], "category": ["done"]})
        if "FROM metrics.fact_values" in query:
            return pl.DataFrame([[1]], schema=["count"])
        raise AssertionError(f"Unexpected query: {query}")

    monkeypatch.setattr(velocity, "read_table", _read_table)
    monkeypatch.setattr(
        velocity.velocity_logic,
        "calculate_velocity_facts",
        lambda **_kwargs: pl.DataFrame(
            {
                "project_id": ["p1"],
                "iteration_id": ["sp-1"],
                "end_date": [date(2026, 1, 7)],
                "planned_story_points": [5.0],
                "completed_story_points": [3.0],
                "planned_issues": [2.0],
                "completed_issues": [1.0],
            }
        ),
    )
    monkeypatch.setattr(
        velocity, "get_slice_rules", lambda *_args, **_kwargs: pl.DataFrame()
    )
    monkeypatch.setattr(
        velocity, "apply_slicing", lambda *_args, **_kwargs: pl.DataFrame()
    )
    monkeypatch.setattr(
        velocity,
        "write_fact_values",
        lambda df, *_args, **_kwargs: df.height,
    )

    out = _asset_fn(velocity.calculate_velocity)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert out["status"] == "success"
    assert out["rows_written"] == 4


def test_calculate_velocity_skipped_no_data_slices_and_check(monkeypatch):
    monkeypatch.setattr(
        velocity, "get_definition_id", lambda *_args, **_kwargs: "def-v"
    )
    monkeypatch.setattr(
        velocity,
        "get_calculation_id",
        lambda _e, c: {
            "velocity_planned_sp": "m1",
            "velocity_completed_sp": "m2",
            "velocity_planned_count": "m3",
            "velocity_completed_count": "m4",
        }[c],
    )
    monkeypatch.setattr(
        velocity, "get_project_agg_id", lambda *_args, **_kwargs: "agg-1"
    )

    monkeypatch.setattr(
        velocity, "read_table", lambda *_args, **_kwargs: pl.DataFrame()
    )
    skipped = _asset_fn(velocity.calculate_velocity)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert skipped["status"] == "skipped"

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.sprints" in query:
            return pl.DataFrame(
                {
                    "id": ["sp-1"],
                    "project_id": ["p1"],
                    "name": ["Sprint 1"],
                    "start_date": [date(2026, 1, 1)],
                    "end_date": [date(2026, 1, 7)],
                    "complete_date": [date(2026, 1, 7)],
                    "project_key": ["P1"],
                }
            )
        if "FROM clean_jira.sprint_issues si" in query:
            return pl.DataFrame({"issue_id": ["i1"], "sprint_id": ["sp-1"]})
        if "FROM clean_jira.sprint_issues_changelog" in query:
            return pl.DataFrame(
                {"issue_id": [], "sprint_id": [], "action": [], "changed_at": []}
            )
        if "FROM clean_jira.issues i" in query:
            return pl.DataFrame(
                {
                    "id": ["i1"],
                    "project_id": ["p1"],
                    "key": ["P1-1"],
                    "type_name": ["Story"],
                    "status_id": ["s1"],
                    "jira_created_at": [datetime(2026, 1, 1)],
                    "jira_resolved_at": [datetime(2026, 1, 7)],
                }
            )
        if "FROM clean_jira.field_keys" in query:
            return pl.DataFrame({"id": ["fk"], "external_key": ["sp"], "name": ["SP"]})
        if "FROM clean_jira.field_values" in query:
            return pl.DataFrame(
                {"issue_id": ["i1"], "field_key_id": ["fk"], "json_value": ["3"]}
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
                    "name": ["Done"],
                    "status_id": ["s1"],
                    "position": [1],
                }
            )
        if "FROM clean_jira.field_value_changelog" in query:
            return pl.DataFrame(
                {
                    "issue_id": [],
                    "field_key_id": [],
                    "old_value": [],
                    "new_value": [],
                    "changed_at": [],
                }
            )
        if "FROM clean_jira.issue_statuses" in query:
            return pl.DataFrame({"id": ["s1"], "name": ["Done"], "category": ["done"]})
        if "FROM metrics.fact_values" in query:
            return pl.DataFrame({"row_count": [2], "negative_count": [0]})
        raise AssertionError(query)

    monkeypatch.setattr(velocity, "read_table", _read_table)
    monkeypatch.setattr(
        velocity.velocity_logic,
        "calculate_velocity_facts",
        lambda **_kwargs: pl.DataFrame(),
    )
    no_data = _asset_fn(velocity.calculate_velocity)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert no_data["status"] == "no_data"

    monkeypatch.setattr(
        velocity.velocity_logic,
        "calculate_velocity_facts",
        lambda **_kwargs: pl.DataFrame(
            {
                "project_id": ["p1"],
                "iteration_id": ["sp-1"],
                "end_date": [date(2026, 1, 7)],
                "planned_story_points": [5.0],
                "completed_story_points": [3.0],
                "planned_issues": [2.0],
                "completed_issues": [1.0],
            }
        ),
    )
    monkeypatch.setattr(
        velocity,
        "get_slice_rules",
        lambda *_args, **_kwargs: pl.DataFrame(
            {
                "slice_rule_id": ["r1"],
                "slice_rule_name": ["By Type"],
                "group_by_column": ["issue_type"],
                "source_table": ["clean_jira.issues"],
                "project_id": [None],
                "enabled": [True],
            }
        ),
    )
    monkeypatch.setattr(
        velocity,
        "apply_slicing",
        lambda *_args, **_kwargs: pl.DataFrame(
            {
                "project_id": ["p1"],
                "iteration_id": ["sp-1"],
                "end_date": [date(2026, 1, 7)],
                "planned_story_points": [2.0],
                "completed_story_points": [1.0],
                "planned_issues": [1.0],
                "completed_issues": [1.0],
                "slice_value": ["Story"],
            }
        ),
    )
    original_concat = pl.concat
    monkeypatch.setattr(
        velocity.pl,
        "concat",
        lambda items: original_concat(items, how="diagonal_relaxed"),
    )
    monkeypatch.setattr(
        velocity, "write_fact_values", lambda df, *_args, **_kwargs: df.height
    )

    out = _asset_fn(velocity.calculate_velocity)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert out["status"] == "success"
    assert out["rows_written"] == 8

    check = _asset_fn(velocity.velocity_data_quality_check)(_DummyDatabase(object()))
    assert check.passed is True


def test_calculate_lead_time_success(monkeypatch):
    monkeypatch.setattr(
        lead_time, "get_definition_id", lambda *_args, **_kwargs: "def-lt"
    )
    monkeypatch.setattr(
        lead_time, "get_calculation_id", lambda *_args, **_kwargs: "lt-id"
    )
    monkeypatch.setattr(
        lead_time, "get_project_agg_id", lambda *_args, **_kwargs: "agg-1"
    )
    monkeypatch.setattr(
        lead_time,
        "resolve_commitment_columns",
        lambda *_args, **_kwargs: {
            "commitment_rule_id": "rule-1",
            "start_column_id": "c1",
            "end_column_id": "c2",
        },
    )
    monkeypatch.setattr(
        lead_time,
        "identify_commitment_points_from_rule",
        lambda *_args, **_kwargs: {
            "middle_status_ids": ["s1"],
            "end_status_ids": ["s2"],
            "commitment_rule_id": "rule-1",
        },
    )

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.issues i" in query:
            return pl.DataFrame(
                {
                    "id": ["i1"],
                    "project_id": ["p1"],
                    "key": ["P1-1"],
                    "type_name": ["Story"],
                    "jira_created_at": [datetime(2026, 1, 1)],
                    "jira_resolved_at": [datetime(2026, 1, 3)],
                    "project_key": ["P1"],
                }
            )
        if "FROM clean_jira.issue_status_changelog" in query:
            return pl.DataFrame(
                {
                    "issue_id": ["i1"],
                    "from_status_id": ["s0"],
                    "to_status_id": ["s2"],
                    "changed_at": [datetime(2026, 1, 2)],
                }
            )
        if "FROM clean_jira.boards" in query:
            return pl.DataFrame({"id": ["b1"], "project_id": ["p1"], "name": ["Board"]})
        if "FROM clean_jira.board_columns bc" in query:
            return pl.DataFrame(
                {
                    "id": ["c1", "c2"],
                    "board_id": ["b1", "b1"],
                    "name": ["In Progress", "Done"],
                    "status_id": ["s1", "s2"],
                    "position": [1, 2],
                }
            )
        if "FROM metrics.fact_values" in query:
            return pl.DataFrame([[1]], schema=["count"])
        raise AssertionError(query)

    monkeypatch.setattr(lead_time, "read_table", _read_table)
    monkeypatch.setattr(
        lead_time.lead_time_logic,
        "calculate_lead_time_per_issue",
        lambda *_args, **_kwargs: pl.DataFrame(
            {
                "issue_id": ["i1"],
                "issue_key": ["P1-1"],
                "project_id": ["p1"],
                "lead_time_days": [2.0],
                "commitment_start_at": [datetime(2026, 1, 1)],
                "commitment_end_at": [datetime(2026, 1, 3)],
            }
        ),
    )
    monkeypatch.setattr(
        lead_time, "get_slice_rules", lambda *_args, **_kwargs: pl.DataFrame()
    )
    monkeypatch.setattr(
        lead_time, "write_fact_values", lambda df, *_args, **_kwargs: df.height
    )

    out = _asset_fn(lead_time.calculate_lead_time)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert out["status"] == "success"
    assert out["rows_written"] == 1


def test_calculate_lead_time_skipped_and_no_data_and_check(monkeypatch):
    monkeypatch.setattr(
        lead_time, "get_definition_id", lambda *_args, **_kwargs: "def-lt"
    )
    monkeypatch.setattr(
        lead_time, "get_calculation_id", lambda *_args, **_kwargs: "lt-id"
    )
    monkeypatch.setattr(
        lead_time, "get_project_agg_id", lambda *_args, **_kwargs: "agg-1"
    )
    monkeypatch.setattr(
        lead_time, "resolve_commitment_columns", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        lead_time,
        "identify_commitment_points_heuristic",
        lambda *_args, **_kwargs: {"middle_status_ids": [], "end_status_ids": []},
    )

    monkeypatch.setattr(
        lead_time, "read_table", lambda *_args, **_kwargs: pl.DataFrame()
    )
    skipped = _asset_fn(lead_time.calculate_lead_time)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert skipped["status"] == "skipped"

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.issues i" in query:
            return pl.DataFrame(
                {
                    "id": ["i1"],
                    "project_id": ["p1"],
                    "key": ["P1-1"],
                    "type_name": ["Story"],
                    "jira_created_at": [datetime(2026, 1, 1)],
                    "jira_resolved_at": [datetime(2026, 1, 3)],
                    "project_key": ["P1"],
                }
            )
        if "FROM clean_jira.issue_status_changelog" in query:
            return pl.DataFrame(
                {
                    "issue_id": ["i1"],
                    "from_status_id": ["s0"],
                    "to_status_id": ["s2"],
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
                    "status_id": ["s1"],
                    "position": [1],
                }
            )
        if "FROM metrics.fact_values" in query:
            return pl.DataFrame([[1]], schema=["count"])
        raise AssertionError(query)

    monkeypatch.setattr(lead_time, "read_table", _read_table)
    no_data = _asset_fn(lead_time.calculate_lead_time)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert no_data["status"] == "no_data"

    check = _asset_fn(lead_time.lead_time_data_quality_check)(_DummyDatabase(object()))
    assert check.passed is True


def test_calculate_lead_time_with_slices(monkeypatch):
    monkeypatch.setattr(
        lead_time, "get_definition_id", lambda *_args, **_kwargs: "def-lt"
    )
    monkeypatch.setattr(
        lead_time, "get_calculation_id", lambda *_args, **_kwargs: "lt-id"
    )
    monkeypatch.setattr(
        lead_time, "get_project_agg_id", lambda *_args, **_kwargs: "agg-1"
    )
    monkeypatch.setattr(
        lead_time,
        "resolve_commitment_columns",
        lambda *_args, **_kwargs: {
            "commitment_rule_id": "rule-1",
            "start_column_id": "c1",
            "end_column_id": "c2",
        },
    )
    monkeypatch.setattr(
        lead_time,
        "identify_commitment_points_from_rule",
        lambda *_args, **_kwargs: {
            "middle_status_ids": ["s1"],
            "end_status_ids": ["s2"],
            "commitment_rule_id": "rule-1",
        },
    )

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.issues i" in query:
            return pl.DataFrame(
                {
                    "id": ["i1"],
                    "project_id": ["p1"],
                    "key": ["P1-1"],
                    "type_name": ["Story"],
                    "jira_created_at": [datetime(2026, 1, 1)],
                    "jira_resolved_at": [datetime(2026, 1, 3)],
                    "project_key": ["P1"],
                }
            )
        if "FROM clean_jira.issue_status_changelog" in query:
            return pl.DataFrame(
                {
                    "issue_id": ["i1"],
                    "from_status_id": ["s0"],
                    "to_status_id": ["s2"],
                    "changed_at": [datetime(2026, 1, 2)],
                }
            )
        if "FROM clean_jira.boards" in query:
            return pl.DataFrame({"id": ["b1"], "project_id": ["p1"], "name": ["Board"]})
        if "FROM clean_jira.board_columns bc" in query:
            return pl.DataFrame(
                {
                    "id": ["c1", "c2"],
                    "board_id": ["b1", "b1"],
                    "name": ["In Progress", "Done"],
                    "status_id": ["s1", "s2"],
                    "position": [1, 2],
                }
            )
        raise AssertionError(query)

    monkeypatch.setattr(lead_time, "read_table", _read_table)
    monkeypatch.setattr(
        lead_time.lead_time_logic,
        "calculate_lead_time_per_issue",
        lambda *_args, **_kwargs: pl.DataFrame(
            {
                "issue_id": ["i1"],
                "issue_key": ["P1-1"],
                "project_id": ["p1"],
                "lead_time_days": [2.0],
                "commitment_start_at": [datetime(2026, 1, 1)],
                "commitment_end_at": [datetime(2026, 1, 3)],
            }
        ),
    )
    monkeypatch.setattr(
        lead_time,
        "get_slice_rules",
        lambda *_args, **_kwargs: pl.DataFrame(
            {
                "slice_rule_id": ["r1"],
                "slice_rule_name": ["By Type"],
                "group_by_column": ["issue_type"],
                "source_table": ["clean_jira.issues"],
                "project_id": [None],
                "enabled": [True],
            }
        ),
    )
    monkeypatch.setattr(
        lead_time,
        "apply_slicing",
        lambda *_args, **_kwargs: pl.DataFrame(
            {
                "issue_id": ["i1"],
                "issue_key": ["P1-1"],
                "project_id": ["p1"],
                "lead_time_days": [2.0],
                "commitment_start_at": [datetime(2026, 1, 1)],
                "commitment_end_at": [datetime(2026, 1, 3)],
                "commitment_rule_id": ["rule-1"],
                "slice_value": ["Story"],
            }
        ),
    )
    original_concat = pl.concat
    monkeypatch.setattr(
        lead_time.pl,
        "concat",
        lambda items: original_concat(items, how="diagonal_relaxed"),
    )
    monkeypatch.setattr(
        lead_time, "write_fact_values", lambda df, *_args, **_kwargs: df.height
    )

    out = _asset_fn(lead_time.calculate_lead_time)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert out["status"] == "success"
    assert out["rows_written"] == 2


def test_calculate_lead_time_passes_middle_and_end_statuses_from_rule(monkeypatch):
    monkeypatch.setattr(
        lead_time, "get_definition_id", lambda *_args, **_kwargs: "def-lt"
    )
    monkeypatch.setattr(
        lead_time, "get_calculation_id", lambda *_args, **_kwargs: "lt-id"
    )
    monkeypatch.setattr(
        lead_time, "get_project_agg_id", lambda *_args, **_kwargs: "agg-1"
    )
    monkeypatch.setattr(
        lead_time, "load_commitment_rules_for_calc", lambda *_args, **_kwargs: []
    )
    monkeypatch.setattr(
        lead_time,
        "resolve_commitment_columns",
        lambda *_args, **_kwargs: {
            "commitment_rule_id": "rule-1",
            "start_column_id": "c1",
            "end_column_id": "c3",
        },
    )
    monkeypatch.setattr(
        lead_time,
        "identify_commitment_points_from_rule",
        lambda *_args, **_kwargs: {
            "middle_status_ids": ["s_in_progress", "s_code_review"],
            "end_status_ids": ["s_done"],
            "commitment_rule_id": "rule-1",
        },
    )

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.issues i" in query:
            return pl.DataFrame(
                {
                    "id": ["i1"],
                    "project_id": ["p1"],
                    "key": ["P1-1"],
                    "type_name": ["Story"],
                    "jira_created_at": [datetime(2026, 1, 1)],
                    "jira_resolved_at": [datetime(2026, 1, 10)],
                    "project_key": ["P1"],
                }
            )
        if "FROM clean_jira.issue_status_changelog" in query:
            return pl.DataFrame(
                {
                    "issue_id": ["i1", "i1"],
                    "from_status_id": [None, "s_code_review"],
                    "to_status_id": ["s_code_review", "s_done"],
                    "changed_at": [datetime(2026, 1, 4), datetime(2026, 1, 9)],
                }
            )
        if "FROM clean_jira.boards" in query:
            return pl.DataFrame({"id": ["b1"], "project_id": ["p1"], "name": ["Board"]})
        if "FROM clean_jira.board_columns bc" in query:
            return pl.DataFrame(
                {
                    "id": ["c1", "c2", "c3"],
                    "board_id": ["b1", "b1", "b1"],
                    "name": ["In Progress", "Code Review", "Done"],
                    "status_id": ["s_in_progress", "s_code_review", "s_done"],
                    "position": [1, 2, 3],
                }
            )
        raise AssertionError(query)

    monkeypatch.setattr(lead_time, "read_table", _read_table)

    captured = {}

    def _calc_lead_time_per_issue(
        _issues_df, _status_changelog_df, middle_status_ids, end_status_ids
    ):
        captured["middle_status_ids"] = middle_status_ids
        captured["end_status_ids"] = end_status_ids
        return pl.DataFrame(
            {
                "issue_id": ["i1"],
                "issue_key": ["P1-1"],
                "project_id": ["p1"],
                "lead_time_days": [5.0],
                "commitment_start_at": [datetime(2026, 1, 4)],
                "commitment_end_at": [datetime(2026, 1, 9)],
            }
        )

    monkeypatch.setattr(
        lead_time.lead_time_logic,
        "calculate_lead_time_per_issue",
        _calc_lead_time_per_issue,
    )
    monkeypatch.setattr(
        lead_time, "get_slice_rules", lambda *_args, **_kwargs: pl.DataFrame()
    )
    monkeypatch.setattr(
        lead_time, "write_fact_values", lambda df, *_args, **_kwargs: df.height
    )

    out = _asset_fn(lead_time.calculate_lead_time)(
        _DummyContext(), _DummyDatabase(object())
    )

    assert out["status"] == "success"
    assert captured["middle_status_ids"] == ["s_in_progress", "s_code_review"]
    assert captured["end_status_ids"] == ["s_done"]


def test_calculate_lead_time_deduplicates_same_issue_from_multiple_boards(monkeypatch):
    monkeypatch.setattr(
        lead_time, "get_definition_id", lambda *_args, **_kwargs: "def-lt"
    )
    monkeypatch.setattr(
        lead_time, "get_calculation_id", lambda *_args, **_kwargs: "lt-id"
    )
    monkeypatch.setattr(
        lead_time, "get_project_agg_id", lambda *_args, **_kwargs: "agg-1"
    )
    monkeypatch.setattr(
        lead_time, "load_commitment_rules_for_calc", lambda *_args, **_kwargs: []
    )
    monkeypatch.setattr(
        lead_time,
        "resolve_commitment_columns",
        lambda *_args, **_kwargs: {
            "commitment_rule_id": "rule-1",
            "start_column_id": "c1",
            "end_column_id": "c2",
        },
    )
    monkeypatch.setattr(
        lead_time,
        "identify_commitment_points_from_rule",
        lambda *_args, **_kwargs: {
            "middle_status_ids": ["s1"],
            "end_status_ids": ["s2"],
            "commitment_rule_id": "rule-1",
        },
    )

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.issues i" in query:
            return pl.DataFrame(
                {
                    "id": ["i1"],
                    "project_id": ["p1"],
                    "key": ["P1-1"],
                    "type_name": ["Story"],
                    "jira_created_at": [datetime(2026, 1, 1)],
                    "jira_resolved_at": [datetime(2026, 1, 10)],
                    "project_key": ["P1"],
                }
            )
        if "FROM clean_jira.issue_status_changelog" in query:
            return pl.DataFrame(
                {
                    "issue_id": ["i1", "i1"],
                    "from_status_id": [None, "s1"],
                    "to_status_id": ["s1", "s2"],
                    "changed_at": [datetime(2026, 1, 2), datetime(2026, 1, 5)],
                }
            )
        if "FROM clean_jira.boards" in query:
            return pl.DataFrame(
                {
                    "id": ["b1", "b2"],
                    "project_id": ["p1", "p1"],
                    "name": ["Board-1", "Board-2"],
                }
            )
        if "FROM clean_jira.board_columns bc" in query:
            return pl.DataFrame(
                {
                    "id": ["c1", "c2", "c3", "c4"],
                    "board_id": ["b1", "b1", "b2", "b2"],
                    "name": ["In Progress", "Done", "In Progress", "Done"],
                    "status_id": ["s1", "s2", "s1", "s2"],
                    "position": [1, 2, 1, 2],
                }
            )
        raise AssertionError(query)

    monkeypatch.setattr(lead_time, "read_table", _read_table)

    def _calc_lead_time_per_issue(
        _issues_df, _status_changelog_df, middle_status_ids, end_status_ids
    ):
        assert middle_status_ids == ["s1"]
        assert end_status_ids == ["s2"]
        return pl.DataFrame(
            {
                "issue_id": ["i1"],
                "issue_key": ["P1-1"],
                "project_id": ["p1"],
                "lead_time_days": [3.0],
                "commitment_start_at": [datetime(2026, 1, 2)],
                "commitment_end_at": [datetime(2026, 1, 5)],
            }
        )

    monkeypatch.setattr(
        lead_time.lead_time_logic,
        "calculate_lead_time_per_issue",
        _calc_lead_time_per_issue,
    )
    monkeypatch.setattr(
        lead_time, "get_slice_rules", lambda *_args, **_kwargs: pl.DataFrame()
    )

    captured = {}

    def _write_fact_values(df, *_args, **_kwargs):
        captured["height"] = df.height
        return df.height

    monkeypatch.setattr(lead_time, "write_fact_values", _write_fact_values)

    out = _asset_fn(lead_time.calculate_lead_time)(
        _DummyContext(), _DummyDatabase(object())
    )

    assert out["status"] == "success"
    assert out["issues_processed"] == 1
    assert captured["height"] == 1


def test_calculate_throughput_success(monkeypatch):
    monkeypatch.setattr(
        throughput, "get_definition_id", lambda *_args, **_kwargs: "def-tp"
    )
    monkeypatch.setattr(
        throughput, "get_calculation_id", lambda *_args, **_kwargs: "tp-id"
    )
    monkeypatch.setattr(
        throughput, "get_project_agg_id", lambda *_args, **_kwargs: "agg-1"
    )

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.issues i" in query:
            return pl.DataFrame(
                {
                    "id": ["i1"],
                    "project_id": ["p1"],
                    "key": ["P1-1"],
                    "type_name": ["Story"],
                    "jira_created_at": [datetime(2026, 1, 1)],
                    "jira_resolved_at": [datetime(2026, 1, 3)],
                    "project_key": ["P1"],
                }
            )
        if "FROM clean_jira.issue_status_changelog" in query:
            return pl.DataFrame(
                {
                    "issue_id": ["i1"],
                    "to_status_id": ["s2"],
                    "changed_at": [datetime(2026, 1, 3)],
                }
            )
        if "FROM clean_jira.boards" in query:
            return pl.DataFrame({"id": ["b1"], "project_id": ["p1"], "name": ["Board"]})
        if "FROM clean_jira.board_columns bc" in query:
            return pl.DataFrame(
                {
                    "id": ["c1"],
                    "board_id": ["b1"],
                    "name": ["Done"],
                    "position": [1],
                    "status_id": ["s2"],
                }
            )
        if "FROM metrics.fact_values" in query:
            return pl.DataFrame([[1]], schema=["count"])
        raise AssertionError(query)

    monkeypatch.setattr(throughput, "read_table", _read_table)
    monkeypatch.setattr(
        throughput.throughput_logic,
        "calculate_weekly_throughput",
        lambda **_kwargs: pl.DataFrame(
            {
                "project_id": ["p1"],
                "week_start_date": [date(2026, 1, 5)],
                "issues_completed": [3.0],
            }
        ),
    )
    monkeypatch.setattr(
        throughput, "get_slice_rules", lambda *_args, **_kwargs: pl.DataFrame()
    )
    monkeypatch.setattr(
        throughput, "write_fact_values", lambda df, *_args, **_kwargs: df.height
    )

    out = _asset_fn(throughput.calculate_throughput)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert out["status"] == "success"
    assert out["rows_written"] == 1


def test_calculate_throughput_skipped_no_data_slices_and_check(monkeypatch):
    monkeypatch.setattr(
        throughput, "get_definition_id", lambda *_args, **_kwargs: "def-tp"
    )
    monkeypatch.setattr(
        throughput, "get_calculation_id", lambda *_args, **_kwargs: "tp-id"
    )
    monkeypatch.setattr(
        throughput, "get_project_agg_id", lambda *_args, **_kwargs: "agg-1"
    )

    monkeypatch.setattr(
        throughput, "read_table", lambda *_args, **_kwargs: pl.DataFrame()
    )
    skipped = _asset_fn(throughput.calculate_throughput)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert skipped["status"] == "skipped"

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.issues i" in query:
            return pl.DataFrame(
                {
                    "id": ["i1"],
                    "project_id": ["p1"],
                    "key": ["P1-1"],
                    "type_name": ["Story"],
                    "jira_created_at": [datetime(2026, 1, 1)],
                    "jira_resolved_at": [datetime(2026, 1, 3)],
                    "project_key": ["P1"],
                }
            )
        if "FROM clean_jira.issue_status_changelog" in query:
            return pl.DataFrame(
                {
                    "issue_id": ["i1"],
                    "to_status_id": ["s2"],
                    "changed_at": [datetime(2026, 1, 3)],
                }
            )
        if "FROM clean_jira.boards" in query:
            return pl.DataFrame({"id": ["b1"], "project_id": ["p1"], "name": ["Board"]})
        if "FROM clean_jira.board_columns bc" in query:
            return pl.DataFrame(
                {
                    "id": ["c1"],
                    "board_id": ["b1"],
                    "name": ["Done"],
                    "position": [1],
                    "status_id": ["s2"],
                }
            )
        if "FROM metrics.fact_values" in query:
            return pl.DataFrame([[1]], schema=["count"])
        raise AssertionError(query)

    monkeypatch.setattr(throughput, "read_table", _read_table)
    monkeypatch.setattr(
        throughput.throughput_logic,
        "calculate_weekly_throughput",
        lambda **_kwargs: pl.DataFrame(),
    )
    no_data = _asset_fn(throughput.calculate_throughput)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert no_data["status"] == "no_data"

    monkeypatch.setattr(
        throughput.throughput_logic,
        "calculate_weekly_throughput",
        lambda **_kwargs: pl.DataFrame(
            {
                "project_id": ["p1"],
                "week_start_date": [date(2026, 1, 5)],
                "issues_completed": [3.0],
            }
        ),
    )
    monkeypatch.setattr(
        throughput,
        "get_slice_rules",
        lambda *_args, **_kwargs: pl.DataFrame(
            {
                "slice_rule_id": ["r1"],
                "slice_rule_name": ["By Type"],
                "group_by_column": ["issue_type"],
                "source_table": ["clean_jira.issues"],
                "project_id": [None],
                "enabled": [True],
            }
        ),
    )
    monkeypatch.setattr(
        throughput,
        "apply_slicing",
        lambda *_args, **_kwargs: pl.DataFrame(
            {
                "project_id": ["p1"],
                "week_start_date": [date(2026, 1, 5)],
                "issues_completed": [1.0],
                "slice_value": ["Story"],
            }
        ),
    )
    original_concat = pl.concat
    monkeypatch.setattr(
        throughput.pl,
        "concat",
        lambda items: original_concat(items, how="diagonal_relaxed"),
    )
    monkeypatch.setattr(
        throughput, "write_fact_values", lambda df, *_args, **_kwargs: df.height
    )
    out = _asset_fn(throughput.calculate_throughput)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert out["status"] == "success"
    assert out["rows_written"] == 2

    check = _asset_fn(throughput.throughput_data_quality_check)(
        _DummyDatabase(object())
    )
    assert check.passed is True


def test_calculate_cfd_success(monkeypatch):
    monkeypatch.setattr(
        cumulative_flow, "get_calculation_id", lambda *_args, **_kwargs: "cfd-id"
    )
    monkeypatch.setattr(
        cumulative_flow, "get_project_agg_id", lambda *_args, **_kwargs: "agg-1"
    )

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.issues i" in query:
            return pl.DataFrame(
                {
                    "id": ["i1"],
                    "project_id": ["p1"],
                    "type_id": ["t1"],
                    "status_id": ["s1"],
                    "jira_created_at": [datetime(2026, 1, 1)],
                    "project_key": ["P1"],
                }
            )
        if "FROM clean_jira.issue_status_changelog" in query:
            return pl.DataFrame(
                {
                    "issue_id": ["i1"],
                    "from_status_id": ["s0"],
                    "to_status_id": ["s1"],
                    "changed_at": [datetime(2026, 1, 1)],
                }
            )
        if "FROM clean_jira.issue_statuses" in query:
            return pl.DataFrame(
                {
                    "id": ["s1"],
                    "project_id": ["p1"],
                    "name": ["To Do"],
                    "category": ["todo"],
                }
            )
        if "FROM clean_jira.boards" in query:
            return pl.DataFrame({"id": ["b1"], "project_id": ["p1"], "name": ["Board"]})
        if "FROM clean_jira.board_columns bc" in query:
            return pl.DataFrame(
                {
                    "id": ["c1"],
                    "board_id": ["b1"],
                    "name": ["To Do"],
                    "position": [1],
                    "status_id": ["s1"],
                }
            )
        if "FROM metrics.fact_values" in query:
            return pl.DataFrame([[1]], schema=["count"])
        raise AssertionError(query)

    monkeypatch.setattr(cumulative_flow, "read_table", _read_table)
    monkeypatch.setattr(
        cumulative_flow.cfd_logic,
        "calculate_cumulative_flow_diagram",
        lambda **_kwargs: pl.DataFrame(
            {
                "project_id": ["p1"],
                "date": [date(2026, 1, 3)],
                "issue_count": [2],
                "column_id": ["c1"],
                "status_id": ["s1"],
            }
        ),
    )
    monkeypatch.setattr(
        cumulative_flow, "write_fact_values", lambda df, *_args, **_kwargs: df.height
    )

    out = _asset_fn(cumulative_flow.calculate_cumulative_flow_diagram)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert out["status"] == "success"
    assert out["rows_written"] == 1


def test_calculate_backlog_growth_success(monkeypatch):
    monkeypatch.setattr(
        backlog_growth, "get_definition_id", lambda *_args, **_kwargs: "def-bg"
    )
    monkeypatch.setattr(
        backlog_growth,
        "get_calculation_id",
        lambda _e, code: {
            "backlog_size": "m1",
            "backlog_created": "m2",
            "backlog_resolved": "m3",
            "backlog_net_growth": "m4",
        }[code],
    )
    monkeypatch.setattr(
        backlog_growth, "get_project_agg_id", lambda *_args, **_kwargs: "agg-1"
    )

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.issues i" in query:
            return pl.DataFrame(
                {
                    "id": ["i1"],
                    "project_id": ["p1"],
                    "type_id": ["t1"],
                    "status_id": ["s1"],
                    "jira_created_at": [datetime(2026, 1, 1)],
                    "jira_updated_at": [datetime(2026, 1, 2)],
                    "jira_resolved_at": [None],
                }
            )
        if "FROM clean_jira.issue_statuses" in query:
            return pl.DataFrame(
                {
                    "id": ["s1"],
                    "project_id": ["p1"],
                    "name": ["To Do"],
                    "category": ["todo"],
                }
            )
        if "FROM clean_jira.issue_types" in query:
            return pl.DataFrame(
                {
                    "id": ["t1"],
                    "project_id": ["p1"],
                    "name": ["Story"],
                    "hierarchy_level": [0],
                }
            )
        if "FROM clean_jira.field_values" in query:
            return pl.DataFrame(
                {"issue_id": ["i1"], "field_key_id": ["fk"], "json_value": ["{}"]}
            )
        if "FROM clean_jira.field_keys" in query:
            return pl.DataFrame(
                {"id": ["fk"], "external_key": ["priority"], "name": ["Priority"]}
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
        if "FROM clean_jira.board_column_statuses" in query:
            return pl.DataFrame(
                {"project_id": ["p1"], "position": [1], "status_id": ["s1"]}
            )
        if "FROM metrics.fact_values" in query:
            return pl.DataFrame([[1]], schema=["count"])
        raise AssertionError(query)

    monkeypatch.setattr(backlog_growth, "read_table", _read_table)
    monkeypatch.setattr(
        backlog_growth.backlog_logic,
        "calculate_backlog_growth",
        lambda **_kwargs: pl.DataFrame(
            {
                "project_id": ["p1"],
                "fact_date": [date(2026, 1, 5)],
                "total_backlog_size": [10.0],
                "created_daily": [3.0],
                "closed_daily": [2.0],
            }
        ),
    )
    monkeypatch.setattr(
        backlog_growth, "get_slice_rules", lambda *_args, **_kwargs: pl.DataFrame()
    )
    monkeypatch.setattr(
        backlog_growth, "write_fact_values", lambda df, *_args, **_kwargs: df.height
    )

    out = _asset_fn(backlog_growth.calculate_backlog_growth)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert out["status"] == "success"
    assert out["rows_written"] == 4


def test_calculate_backlog_growth_no_data(monkeypatch):
    monkeypatch.setattr(
        backlog_growth, "get_definition_id", lambda *_args, **_kwargs: "def-bg"
    )
    monkeypatch.setattr(
        backlog_growth,
        "get_calculation_id",
        lambda _e, code: {
            "backlog_size": "m1",
            "backlog_created": "m2",
            "backlog_resolved": "m3",
            "backlog_net_growth": "m4",
        }[code],
    )
    monkeypatch.setattr(
        backlog_growth, "get_project_agg_id", lambda *_args, **_kwargs: "agg-1"
    )

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.issues i" in query:
            return pl.DataFrame(
                {
                    "id": ["i1"],
                    "project_id": ["p1"],
                    "type_id": ["t1"],
                    "status_id": ["s1"],
                    "jira_created_at": [datetime(2026, 1, 1)],
                    "jira_updated_at": [datetime(2026, 1, 2)],
                    "jira_resolved_at": [None],
                }
            )
        if "FROM clean_jira.issue_statuses" in query:
            return pl.DataFrame(
                {
                    "id": ["s1"],
                    "project_id": ["p1"],
                    "name": ["To Do"],
                    "category": ["todo"],
                }
            )
        if "FROM clean_jira.issue_types" in query:
            return pl.DataFrame(
                {
                    "id": ["t1"],
                    "project_id": ["p1"],
                    "name": ["Story"],
                    "hierarchy_level": [0],
                }
            )
        if "FROM clean_jira.field_values" in query:
            return pl.DataFrame(
                {"issue_id": ["i1"], "field_key_id": ["fk"], "json_value": ["{}"]}
            )
        if "FROM clean_jira.field_keys" in query:
            return pl.DataFrame(
                {"id": ["fk"], "external_key": ["priority"], "name": ["Priority"]}
            )
        if "FROM clean_jira.issue_status_changelog" in query:
            return pl.DataFrame(
                {
                    "issue_id": [],
                    "from_status_id": [],
                    "to_status_id": [],
                    "changed_at": [],
                }
            )
        if "FROM clean_jira.board_column_statuses" in query:
            return pl.DataFrame(
                {"project_id": ["p1"], "position": [1], "status_id": ["s1"]}
            )
        raise AssertionError(query)

    monkeypatch.setattr(backlog_growth, "read_table", _read_table)
    monkeypatch.setattr(
        backlog_growth.backlog_logic,
        "calculate_backlog_growth",
        lambda **_kwargs: pl.DataFrame(),
    )

    out = _asset_fn(backlog_growth.calculate_backlog_growth)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert out["status"] == "no_data"


def test_calculate_backlog_growth_with_slices_and_check(monkeypatch):
    monkeypatch.setattr(
        backlog_growth, "get_definition_id", lambda *_args, **_kwargs: "def-bg"
    )
    monkeypatch.setattr(
        backlog_growth,
        "get_calculation_id",
        lambda _e, code: {
            "backlog_size": "m1",
            "backlog_created": "m2",
            "backlog_resolved": "m3",
            "backlog_net_growth": "m4",
        }[code],
    )
    monkeypatch.setattr(
        backlog_growth, "get_project_agg_id", lambda *_args, **_kwargs: "agg-1"
    )

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.issues i" in query:
            return pl.DataFrame(
                {
                    "id": ["i1"],
                    "project_id": ["p1"],
                    "type_id": ["t1"],
                    "status_id": ["s1"],
                    "jira_created_at": [datetime(2026, 1, 1)],
                    "jira_updated_at": [datetime(2026, 1, 2)],
                    "jira_resolved_at": [None],
                }
            )
        if "FROM clean_jira.issue_statuses" in query:
            return pl.DataFrame(
                {
                    "id": ["s1"],
                    "project_id": ["p1"],
                    "name": ["To Do"],
                    "category": ["todo"],
                }
            )
        if "FROM clean_jira.issue_types" in query:
            return pl.DataFrame(
                {
                    "id": ["t1"],
                    "project_id": ["p1"],
                    "name": ["Story"],
                    "hierarchy_level": [0],
                }
            )
        if "FROM clean_jira.field_values" in query:
            return pl.DataFrame(
                {"issue_id": ["i1"], "field_key_id": ["fk"], "json_value": ["{}"]}
            )
        if "FROM clean_jira.field_keys" in query:
            return pl.DataFrame(
                {"id": ["fk"], "external_key": ["priority"], "name": ["Priority"]}
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
        if "FROM clean_jira.board_column_statuses" in query:
            return pl.DataFrame(
                {"project_id": ["p1"], "position": [1], "status_id": ["s1"]}
            )
        if "FROM metrics.fact_values" in query:
            return pl.DataFrame({"row_count": [2], "negative_count": [0]})
        raise AssertionError(query)

    monkeypatch.setattr(backlog_growth, "read_table", _read_table)
    monkeypatch.setattr(
        backlog_growth.backlog_logic,
        "calculate_backlog_growth",
        lambda **_kwargs: pl.DataFrame(
            {
                "project_id": ["p1"],
                "fact_date": [date(2026, 1, 5)],
                "total_backlog_size": [10.0],
                "created_daily": [3.0],
                "closed_daily": [2.0],
            }
        ),
    )
    monkeypatch.setattr(
        backlog_growth,
        "get_slice_rules",
        lambda *_args, **_kwargs: pl.DataFrame(
            {
                "slice_rule_id": ["r1"],
                "slice_rule_name": ["By Type"],
                "group_by_column": ["issue_type"],
                "source_table": ["clean_jira.issues"],
                "project_id": [None],
                "enabled": [True],
            }
        ),
    )
    monkeypatch.setattr(
        backlog_growth,
        "apply_slicing",
        lambda *_args, **_kwargs: pl.DataFrame(
            {
                "project_id": ["p1"],
                "fact_date": [date(2026, 1, 5)],
                "total_backlog_size": [4.0],
                "created_daily": [1.0],
                "closed_daily": [0.0],
                "net_growth_daily": [1.0],
                "slice_value": ["Story"],
            }
        ),
    )
    original_concat = pl.concat
    monkeypatch.setattr(
        backlog_growth.pl,
        "concat",
        lambda items: original_concat(items, how="diagonal_relaxed"),
    )
    monkeypatch.setattr(
        backlog_growth, "write_fact_values", lambda df, *_args, **_kwargs: df.height
    )

    out = _asset_fn(backlog_growth.calculate_backlog_growth)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert out["status"] == "success"
    assert out["rows_written"] == 8

    check = _asset_fn(backlog_growth.backlog_growth_data_quality_check)(
        _DummyDatabase(object())
    )
    assert check.passed is True


def test_calculate_ttm_success(monkeypatch):
    monkeypatch.setattr(
        time_to_market, "get_definition_id", lambda *_args, **_kwargs: "def-ttm"
    )
    monkeypatch.setattr(
        time_to_market, "get_calculation_id", lambda *_args, **_kwargs: "ttm-id"
    )
    monkeypatch.setattr(
        time_to_market, "get_project_agg_id", lambda *_args, **_kwargs: "agg-1"
    )

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.issues i" in query:
            return pl.DataFrame(
                {
                    "id": ["i1"],
                    "project_id": ["p1"],
                    "key": ["P1-1"],
                    "type_id": ["t1"],
                    "type_name": ["Epic"],
                    "jira_created_at": [datetime(2026, 1, 1)],
                    "jira_resolved_at": [datetime(2026, 1, 4)],
                }
            )
        if "FROM clean_jira.projects p" in query:
            return pl.DataFrame({"id": ["p1"], "external_key": ["P1"]})
        if "FROM clean_jira.issue_types" in query:
            return pl.DataFrame(
                {"id": ["t1"], "name": ["Epic"], "hierarchy_level": [1]}
            )
        if "FROM clean_jira.boards" in query:
            return pl.DataFrame({"id": ["b1"], "project_id": ["p1"], "name": ["B1"]})
        if "FROM clean_jira.board_columns bc" in query:
            return pl.DataFrame(
                {
                    "id": ["c1"],
                    "board_id": ["b1"],
                    "name": ["Done"],
                    "position": [1.0],
                    "status_id": ["done"],
                }
            )
        if "FROM metrics.calculation_settings s" in query:
            return pl.DataFrame()
        if "FROM clean_jira.issue_status_changelog" in query:
            return pl.DataFrame(
                {
                    "issue_id": ["i1"],
                    "to_status_id": ["done"],
                    "changed_at": [datetime(2026, 1, 4)],
                }
            )
        if "FROM metrics.fact_values" in query:
            return pl.DataFrame([[1]], schema=["count"])
        raise AssertionError(query)

    monkeypatch.setattr(time_to_market, "read_table", _read_table)
    monkeypatch.setattr(
        time_to_market.ttm_logic,
        "load_issue_type_filter",
        lambda *_args, **_kwargs: ["Epic"],
    )
    monkeypatch.setattr(
        time_to_market,
        "load_commitment_rules_for_calc",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        time_to_market.lead_time_logic,
        "calculate_lead_time_per_issue",
        lambda **_kwargs: pl.DataFrame(
            {
                "issue_id": ["i1"],
                "project_id": ["p1"],
                "commitment_end_at": [datetime(2026, 1, 10)],
                "lead_time_days": [9.0],
                "issue_key": ["P1-1"],
                "commitment_start_at": [datetime(2026, 1, 1)],
            }
        ),
    )
    monkeypatch.setattr(
        time_to_market, "get_slice_rules", lambda *_args, **_kwargs: pl.DataFrame()
    )
    monkeypatch.setattr(
        time_to_market, "write_fact_values", lambda df, *_args, **_kwargs: df.height
    )

    out = _asset_fn(time_to_market.calculate_time_to_market)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert out["status"] == "success"
    assert out["rows_written"] == 1


def test_calculate_ttm_skipped_no_data_slices_and_check(monkeypatch):
    monkeypatch.setattr(
        time_to_market, "get_definition_id", lambda *_args, **_kwargs: "def-ttm"
    )
    monkeypatch.setattr(
        time_to_market, "get_calculation_id", lambda *_args, **_kwargs: "ttm-id"
    )
    monkeypatch.setattr(
        time_to_market, "get_project_agg_id", lambda *_args, **_kwargs: "agg-1"
    )

    monkeypatch.setattr(
        time_to_market, "read_table", lambda *_args, **_kwargs: pl.DataFrame()
    )
    skipped = _asset_fn(time_to_market.calculate_time_to_market)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert skipped["status"] == "skipped"

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.issues i" in query:
            return pl.DataFrame(
                {
                    "id": ["i1"],
                    "project_id": ["p1"],
                    "key": ["P1-1"],
                    "type_id": ["t1"],
                    "type_name": ["Epic"],
                    "jira_created_at": [datetime(2026, 1, 1)],
                    "jira_resolved_at": [datetime(2026, 1, 4)],
                }
            )
        if "FROM clean_jira.projects p" in query:
            return pl.DataFrame({"id": ["p1"], "external_key": ["P1"]})
        if "FROM clean_jira.issue_types" in query:
            return pl.DataFrame(
                {"id": ["t1"], "name": ["Epic"], "hierarchy_level": [1]}
            )
        if "FROM clean_jira.boards" in query:
            return pl.DataFrame({"id": ["b1"], "project_id": ["p1"], "name": ["B1"]})
        if "FROM clean_jira.board_columns bc" in query:
            return pl.DataFrame(
                {
                    "id": ["c1"],
                    "board_id": ["b1"],
                    "name": ["Done"],
                    "position": [1.0],
                    "status_id": ["done"],
                }
            )
        if "FROM metrics.calculation_settings s" in query:
            return pl.DataFrame()
        if "FROM clean_jira.issue_status_changelog" in query:
            return pl.DataFrame(
                {
                    "issue_id": ["i1"],
                    "to_status_id": ["done"],
                    "changed_at": [datetime(2026, 1, 4)],
                }
            )
        if "FROM metrics.fact_values" in query:
            return pl.DataFrame([[1]], schema=["count"])
        raise AssertionError(query)

    monkeypatch.setattr(time_to_market, "read_table", _read_table)
    monkeypatch.setattr(
        time_to_market.ttm_logic,
        "load_issue_type_filter",
        lambda *_args, **_kwargs: ["Epic"],
    )
    monkeypatch.setattr(
        time_to_market,
        "load_commitment_rules_for_calc",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        time_to_market.lead_time_logic,
        "calculate_lead_time_per_issue",
        lambda **_kwargs: pl.DataFrame(),
    )
    no_data = _asset_fn(time_to_market.calculate_time_to_market)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert no_data["status"] == "no_data"

    monkeypatch.setattr(
        time_to_market.lead_time_logic,
        "calculate_lead_time_per_issue",
        lambda **_kwargs: pl.DataFrame(
            {
                "issue_id": ["i1"],
                "project_id": ["p1"],
                "commitment_end_at": [datetime(2026, 1, 10)],
                "lead_time_days": [9.0],
                "issue_key": ["P1-1"],
                "commitment_start_at": [datetime(2026, 1, 1)],
            }
        ),
    )
    monkeypatch.setattr(
        time_to_market,
        "get_slice_rules",
        lambda *_args, **_kwargs: pl.DataFrame(
            {
                "slice_rule_id": ["r1"],
                "slice_rule_name": ["By Team"],
                "group_by_column": ["slice_value"],
                "source_table": ["metrics"],
                "project_id": [None],
                "enabled": [True],
            }
        ),
    )
    monkeypatch.setattr(
        time_to_market,
        "apply_slicing",
        lambda *_args, **_kwargs: pl.DataFrame(
            {
                "project_id": ["p1"],
                "released_at": [datetime(2026, 1, 10)],
                "time_to_market_days": [9.0],
                "issue_key": ["P1-1"],
                "jira_created_at": [datetime(2026, 1, 1)],
                "slice_value": ["Team A"],
            }
        ),
    )
    original_concat = pl.concat
    monkeypatch.setattr(
        time_to_market.pl,
        "concat",
        lambda items: original_concat(items, how="diagonal_relaxed"),
    )
    monkeypatch.setattr(
        time_to_market, "write_fact_values", lambda df, *_args, **_kwargs: df.height
    )
    out = _asset_fn(time_to_market.calculate_time_to_market)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert out["status"] == "success"
    assert out["rows_written"] == 2

    check = _asset_fn(time_to_market.ttm_data_quality_check)(_DummyDatabase(object()))
    assert check.passed is True


def test_refresh_assets_and_checks():
    engine = _FakeEngine(
        [
            _FakeResult(mapping={"total_issues": 1}),
            _FakeResult(mapping={"total_sprints": 2}),
            _FakeResult(mapping={"total_weeks": 3}),
            _FakeResult(mapping={"lead_time_records": 4}),
            _FakeResult(scalar_value=0),
            _FakeResult(scalar_value=0),
            _FakeResult(scalar_value=0),
            _FakeResult(scalar_value=0),
        ]
    )
    db = _DummyDatabase(engine)

    lead = _asset_fn(refresh.metrics_lead_time)(_DummyContext(), db)
    vel = _asset_fn(refresh.metrics_velocity)(_DummyContext(), db)
    thr = _asset_fn(refresh.metrics_throughput)(_DummyContext(), db)
    all_stats = _asset_fn(refresh.metrics_all)(_DummyContext(), db)

    assert lead["status"] == "success"
    assert vel["status"] == "success"
    assert thr["status"] == "success"
    assert all_stats["status"] == "success"

    check1 = _asset_fn(refresh.check_lead_time_no_nulls)(None, db)
    check2 = _asset_fn(refresh.check_lead_time_positive)(None, db)
    check3 = _asset_fn(refresh.check_velocity_completion_rate_valid)(None, db)
    check4 = _asset_fn(refresh.check_throughput_no_future_dates)(None, db)

    assert check1.passed is True
    assert check2.passed is True
    assert check3.passed is True
    assert check4.passed is True
