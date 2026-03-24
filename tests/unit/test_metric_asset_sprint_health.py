from datetime import datetime

import polars as pl

from pipelines.assets.metrics import sprint_health


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


def test_calculate_sprint_health_skipped_no_sprints(monkeypatch):
    monkeypatch.setattr(sprint_health, "get_definition_id", lambda *_a, **_k: "d1")
    monkeypatch.setattr(sprint_health, "get_calculation_id", lambda *_a, **_k: "m1")
    monkeypatch.setattr(sprint_health, "read_table", lambda *_a, **_k: pl.DataFrame())
    out = _asset_fn(sprint_health.calculate_sprint_health)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert out["status"] == "skipped"


def test_calculate_sprint_health_success(monkeypatch):
    calc_ids = {
        "sprint_added_issues_count": "m1",
        "sprint_added_sp_sum": "m2",
        "sprint_removed_issues_count": "m3",
        "sprint_removed_sp_sum": "m4",
        "sprint_spillover_count": "m5",
        "sprint_burndown_remaining_sp": "m6",
        "activation_velocity_pct": "m7",
        "unestimated_closed_count": "m8",
        "field_value_sprint_pct": "m9",
    }
    monkeypatch.setattr(sprint_health, "get_definition_id", lambda *_a, **_k: "d1")
    monkeypatch.setattr(
        sprint_health, "get_calculation_id", lambda _e, code: calc_ids[code]
    )
    monkeypatch.setattr(sprint_health, "get_project_agg_id", lambda *_a, **_k: "agg-1")
    monkeypatch.setattr(
        sprint_health, "write_fact_values", lambda df, *_a, **_k: df.height
    )

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.sprints" in query:
            return pl.DataFrame(
                {
                    "id": ["S1"],
                    "project_id": ["P1"],
                    "start_date": [datetime(2026, 1, 1)],
                    "end_date": [datetime(2026, 1, 14)],
                    "complete_date": [datetime(2026, 1, 14)],
                }
            )
        if "FROM clean_jira.sprint_issues_changelog" in query:
            return pl.DataFrame(
                {
                    "issue_id": ["I1"],
                    "sprint_id": ["S1"],
                    "action": ["added"],
                    "changed_at": [datetime(2026, 1, 1)],
                }
            )
        if "FROM clean_jira.sprint_issues" in query:
            return pl.DataFrame({"issue_id": ["I1"], "sprint_id": ["S1"]})
        if "FROM clean_jira.issues i" in query:
            return pl.DataFrame(
                {
                    "id": ["I1"],
                    "project_id": ["P1"],
                    "issue_key": ["P1-1"],
                    "created_at": [datetime(2025, 12, 1)],
                    "updated_at": [datetime(2026, 1, 2)],
                    "issue_type_id": ["T1"],
                    "type_name": ["Story"],
                }
            )
        if "FROM clean_jira.field_keys" in query:
            return pl.DataFrame(
                {
                    "id": ["SP", "PR"],
                    "external_key": ["customfield_10036", "priority"],
                    "name": ["Story Points", "Priority"],
                }
            )
        if "FROM clean_jira.field_values" in query:
            return pl.DataFrame(
                {
                    "issue_id": ["I1"],
                    "field_key_id": ["SP"],
                    "json_value": ["5"],
                }
            )
        if "FROM clean_jira.field_value_changelog" in query:
            return pl.DataFrame(
                schema={
                    "issue_id": pl.Utf8,
                    "field_key_id": pl.Utf8,
                    "old_value": pl.Utf8,
                    "new_value": pl.Utf8,
                    "change_time": pl.Datetime,
                }
            )
        if "FROM clean_jira.issue_status_changelog" in query:
            return pl.DataFrame(
                {
                    "issue_id": ["I1"],
                    "from_status_id": ["TODO"],
                    "to_status_id": ["DONE"],
                    "changed_at": [datetime(2026, 1, 3)],
                }
            )
        if "FROM clean_jira.board_columns bc" in query:
            return pl.DataFrame(
                {
                    "id": ["C1"],
                    "board_id": ["B1"],
                    "name": ["Done"],
                    "status_id": ["DONE"],
                    "position": [1],
                }
            )
        if "FROM clean_jira.boards" in query:
            return pl.DataFrame({"id": ["B1"], "project_id": ["P1"]})
        if "FROM metrics.calculation_settings" in query:
            return pl.DataFrame(
                {
                    "id": ["SET1"],
                    "target_calculation_id": [params["cid"]],
                    "project_id": [None],
                    "enabled": [True],
                    "settings_json": [
                        {"field_name": "priority", "field_value": "High"}
                    ],
                }
            )
        raise AssertionError(query)

    monkeypatch.setattr(sprint_health, "read_table", _read_table)
    monkeypatch.setattr(
        sprint_health,
        "load_commitment_rules_for_calc",
        lambda *_a, **_k: pl.DataFrame({"r": [1]}),
    )
    monkeypatch.setattr(
        sprint_health, "resolve_rule_from_cache", lambda *_a, **_k: {"id": "r1"}
    )
    monkeypatch.setattr(
        sprint_health,
        "identify_commitment_points_from_rule",
        lambda *_a, **_k: {"start_status_ids": ["TODO"], "end_status_ids": ["DONE"]},
    )

    monkeypatch.setattr(
        sprint_health.sprint_health_logic,
        "calculate_sprint_scope_changes",
        lambda *_a, **_k: pl.DataFrame(
            {
                "project_id": ["P1"],
                "time_date": [datetime(2026, 1, 1)],
                "iteration_id": ["S1"],
                "added_count": [1],
                "added_sp": [3.0],
                "removed_count": [0],
                "removed_sp": [0.0],
            }
        ),
    )
    monkeypatch.setattr(
        sprint_health.sprint_health_logic,
        "calculate_sprint_spillover",
        lambda *_a, **_k: pl.DataFrame(
            {
                "project_id": ["P1"],
                "start_date": [datetime(2026, 1, 1)],
                "iteration_id": ["S1"],
                "spillover_count": [0],
            }
        ),
    )
    monkeypatch.setattr(
        sprint_health.sprint_health_logic,
        "calculate_sprint_burndown",
        lambda *_a, **_k: pl.DataFrame(
            {
                "project_id": ["P1"],
                "time_date": [datetime(2026, 1, 2)],
                "iteration_id": ["S1"],
                "remaining_sp": [2.0],
            }
        ),
    )
    monkeypatch.setattr(
        sprint_health.sprint_health_logic,
        "calculate_activation_velocity",
        lambda *_a, **_k: pl.DataFrame(
            {
                "project_id": ["P1"],
                "time_date": [datetime(2026, 1, 2)],
                "iteration_id": ["S1"],
                "activation_pct": [50.0],
            }
        ),
    )
    monkeypatch.setattr(
        sprint_health.sprint_health_logic,
        "calculate_unestimated_closed",
        lambda *_a, **_k: pl.DataFrame(
            {
                "project_id": ["P1"],
                "start_date": [datetime(2026, 1, 1)],
                "iteration_id": ["S1"],
                "unestimated_count": [1],
            }
        ),
    )
    monkeypatch.setattr(
        sprint_health.sprint_health_logic,
        "calculate_field_value_sprint_pct",
        lambda *_a, **_k: pl.DataFrame(
            {
                "project_id": ["P1"],
                "start_date": [datetime(2026, 1, 1)],
                "iteration_id": ["S1"],
                "field_pct": [25.0],
            }
        ),
    )

    out = _asset_fn(sprint_health.calculate_sprint_health)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert out["status"] == "success"
    assert out["rows_written"] > 0
    assert out["metrics_calculated"] >= 5


def test_sprint_health_data_quality_check_fail_and_pass(monkeypatch):
    calc_ids = {
        "sprint_added_issues_count": "m1",
        "sprint_added_sp_sum": "m2",
        "sprint_removed_issues_count": "m3",
        "sprint_removed_sp_sum": "m4",
        "sprint_spillover_count": "m5",
        "sprint_burndown_remaining_sp": "m6",
    }
    monkeypatch.setattr(
        sprint_health, "get_calculation_id", lambda _e, code: calc_ids[code]
    )

    responses = [
        pl.DataFrame({"cnt": [0]}),
        pl.DataFrame({"cnt": [1]}),
    ]

    def _read_table(_engine, _query, params=None):
        return responses.pop(0)

    monkeypatch.setattr(sprint_health, "read_table", _read_table)
    failed = _asset_fn(sprint_health.sprint_health_data_quality_check)(
        _DummyDatabase(object())
    )
    assert failed.passed is False

    monkeypatch.setattr(
        sprint_health, "read_table", lambda *_a, **_k: pl.DataFrame({"cnt": [0]})
    )
    passed = _asset_fn(sprint_health.sprint_health_data_quality_check)(
        _DummyDatabase(object())
    )
    assert passed.passed is True
