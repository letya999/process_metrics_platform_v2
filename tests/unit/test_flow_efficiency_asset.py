from datetime import datetime

import polars as pl

from pipelines.assets.metrics import flow_efficiency


def _asset_fn(defn):
    return defn.node_def.compute_fn.decorated_fn


class _DummyLog:
    def __init__(self):
        self.warnings = []

    def info(self, *_args, **_kwargs):
        return None

    def warning(self, msg, *_args, **_kwargs):
        self.warnings.append(str(msg))


class _DummyContext:
    def __init__(self):
        self.log = _DummyLog()


class _DummyDatabase:
    def __init__(self, engine):
        self._engine = engine

    def get_engine(self):
        return self._engine


def _common_mocks(monkeypatch):
    monkeypatch.setattr(
        flow_efficiency, "get_definition_id", lambda *_a, **_k: "def-flow"
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
        flow_efficiency, "get_project_agg_id", lambda _e, pid: f"agg-{pid}"
    )
    monkeypatch.setattr(
        flow_efficiency, "write_fact_values", lambda df, *_a, **_k: df.height
    )


def _base_tables():
    issues_df = pl.DataFrame(
        {
            "id": ["i1", "i2"],
            "project_id": ["p1", "p2"],
            "key": ["P1-1", "P2-1"],
            "type_name": ["Story", "Story"],
            "status_id": ["s1", "s4"],
            "jira_created_at": [datetime(2026, 1, 1), datetime(2026, 1, 1)],
            "project_key": ["P1", "P2"],
        }
    )
    statuses_df = pl.DataFrame(
        {
            "id": ["s1", "s2", "s3", "s4", "s5", "s6"],
            "project_id": ["p1", "p1", "p1", "p2", "p2", "p2"],
            "name": ["In Progress", "To Do", "Done", "In Progress", "To Do", "Done"],
            "category": [
                "in_progress",
                "to_do",
                "done",
                "in_progress",
                "to_do",
                "done",
            ],
        }
    )
    changelog_df = pl.DataFrame(
        {
            "issue_id": ["i1", "i2"],
            "from_status_id": ["s2", "s5"],
            "to_status_id": ["s1", "s4"],
            "changed_at": [datetime(2026, 1, 2), datetime(2026, 1, 2)],
        }
    )
    return issues_df, statuses_df, changelog_df


def test_flow_efficiency_skips_project_without_settings(monkeypatch):
    _common_mocks(monkeypatch)
    issues_df, statuses_df, changelog_df = _base_tables()

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.issues i" in query:
            return issues_df
        if "FROM clean_jira.issue_status_changelog" in query:
            return changelog_df
        if "FROM clean_jira.issue_statuses" in query:
            return statuses_df
        if "metrics.calculation_settings" in query:
            return pl.DataFrame(
                {
                    "project_id": ["p1"],
                    "settings_json": [
                        {
                            "active_categories": ["in_progress"],
                            "passive_categories": ["to_do"],
                            "done_categories": ["done"],
                        }
                    ],
                }
            )
        raise AssertionError(query)

    called_projects = []

    def _calc(**kwargs):
        called_projects.append(kwargs["issues_df"][0, "project_id"])
        return pl.DataFrame(
            {
                "issue_id": [kwargs["issues_df"][0, "id"]],
                "project_id": [kwargs["issues_df"][0, "project_id"]],
                "issue_key": [kwargs["issues_df"][0, "key"]],
                "active_days": [2.0],
                "wait_days": [1.0],
                "efficiency_pct": [66.67],
                "completion_date": [datetime(2026, 1, 5)],
            }
        )

    monkeypatch.setattr(flow_efficiency, "read_table", _read_table)
    monkeypatch.setattr(
        flow_efficiency.flow_logic, "calculate_flow_efficiency_per_issue", _calc
    )
    monkeypatch.setattr(
        flow_efficiency, "get_slice_rules", lambda *_a, **_k: pl.DataFrame()
    )

    ctx = _DummyContext()
    out = _asset_fn(flow_efficiency.calculate_flow_efficiency)(
        ctx, _DummyDatabase(object())
    )

    assert out["status"] == "success"
    assert called_projects == ["p1"]
    assert any("skipping" in w.lower() for w in ctx.log.warnings)


def test_flow_efficiency_uses_settings_per_project(monkeypatch):
    _common_mocks(monkeypatch)
    issues_df, statuses_df, changelog_df = _base_tables()

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.issues i" in query:
            return issues_df
        if "FROM clean_jira.issue_status_changelog" in query:
            return changelog_df
        if "FROM clean_jira.issue_statuses" in query:
            return statuses_df
        if "metrics.calculation_settings" in query:
            return pl.DataFrame(
                {
                    "project_id": ["p1", "p2"],
                    "settings_json": [
                        {
                            "active_categories": ["in_progress"],
                            "passive_categories": ["to_do"],
                            "done_categories": ["done"],
                        },
                        {
                            "active_categories": ["to_do"],
                            "passive_categories": ["in_progress"],
                            "done_categories": ["done"],
                        },
                    ],
                }
            )
        raise AssertionError(query)

    by_project = {}

    def _calc(**kwargs):
        p = kwargs["issues_df"][0, "project_id"]
        by_project[p] = (
            kwargs["active_status_ids"],
            kwargs["wait_status_ids"],
            kwargs["end_status_ids"],
        )
        return pl.DataFrame(
            {
                "issue_id": [kwargs["issues_df"][0, "id"]],
                "project_id": [p],
                "issue_key": [kwargs["issues_df"][0, "key"]],
                "active_days": [1.0],
                "wait_days": [1.0],
                "efficiency_pct": [50.0],
                "completion_date": [datetime(2026, 1, 5)],
            }
        )

    monkeypatch.setattr(flow_efficiency, "read_table", _read_table)
    monkeypatch.setattr(
        flow_efficiency.flow_logic, "calculate_flow_efficiency_per_issue", _calc
    )
    monkeypatch.setattr(
        flow_efficiency, "get_slice_rules", lambda *_a, **_k: pl.DataFrame()
    )

    out = _asset_fn(flow_efficiency.calculate_flow_efficiency)(
        _DummyContext(), _DummyDatabase(object())
    )

    assert out["status"] == "success"
    assert by_project["p1"][0] == ["s1"]
    assert by_project["p1"][1] == ["s2"]
    assert by_project["p2"][0] == ["s5"]
    assert by_project["p2"][1] == ["s4"]


def test_flow_efficiency_skips_all_when_no_settings(monkeypatch):
    _common_mocks(monkeypatch)
    issues_df, statuses_df, changelog_df = _base_tables()

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.issues i" in query:
            return issues_df
        if "FROM clean_jira.issue_status_changelog" in query:
            return changelog_df
        if "FROM clean_jira.issue_statuses" in query:
            return statuses_df
        if "metrics.calculation_settings" in query:
            return pl.DataFrame(
                schema={"project_id": pl.Utf8, "settings_json": pl.Object}
            )
        raise AssertionError(query)

    monkeypatch.setattr(flow_efficiency, "read_table", _read_table)
    monkeypatch.setattr(
        flow_efficiency.flow_logic,
        "calculate_flow_efficiency_per_issue",
        lambda **_kwargs: pl.DataFrame(),
    )
    monkeypatch.setattr(
        flow_efficiency, "get_slice_rules", lambda *_a, **_k: pl.DataFrame()
    )

    out = _asset_fn(flow_efficiency.calculate_flow_efficiency)(
        _DummyContext(), _DummyDatabase(object())
    )
    assert out == {"status": "no_data"}


def test_flow_efficiency_slice_calc_uses_project_status_maps(monkeypatch):
    _common_mocks(monkeypatch)
    issues_df, statuses_df, changelog_df = _base_tables()

    def _read_table(_engine, query, params=None):
        if "FROM clean_jira.issues i" in query:
            return issues_df
        if "FROM clean_jira.issue_status_changelog" in query:
            return changelog_df
        if "FROM clean_jira.issue_statuses" in query:
            return statuses_df
        if "metrics.calculation_settings" in query:
            return pl.DataFrame(
                {
                    "project_id": ["p1", "p2"],
                    "settings_json": [
                        {
                            "active_categories": ["in_progress"],
                            "passive_categories": ["to_do"],
                            "done_categories": ["done"],
                        },
                        {
                            "active_categories": ["to_do"],
                            "passive_categories": ["in_progress"],
                            "done_categories": ["done"],
                        },
                    ],
                }
            )
        raise AssertionError(query)

    slice_calls = []

    def _calc(**kwargs):
        p = kwargs["issues_df"][0, "project_id"]
        slice_calls.append(
            (p, tuple(kwargs["active_status_ids"]), tuple(kwargs["wait_status_ids"]))
        )
        return pl.DataFrame(
            {
                "issue_id": [kwargs["issues_df"][0, "id"]],
                "project_id": [p],
                "issue_key": [kwargs["issues_df"][0, "key"]],
                "active_days": [2.0],
                "wait_days": [1.0],
                "efficiency_pct": [66.67],
                "completion_date": [datetime(2026, 1, 5)],
            }
        )

    def _apply_slicing(df, _rule_df, calc_fn, engine=None):
        out = calc_fn(df)
        if out.is_empty():
            return out
        return out.with_columns(pl.lit("Story").alias("slice_value"))

    monkeypatch.setattr(flow_efficiency, "read_table", _read_table)
    monkeypatch.setattr(
        flow_efficiency.flow_logic, "calculate_flow_efficiency_per_issue", _calc
    )
    monkeypatch.setattr(
        flow_efficiency,
        "get_slice_rules",
        lambda *_a, **_k: pl.DataFrame({"slice_rule_id": ["rule-1"]}),
    )
    monkeypatch.setattr(flow_efficiency, "apply_slicing", _apply_slicing)

    out = _asset_fn(flow_efficiency.calculate_flow_efficiency)(
        _DummyContext(), _DummyDatabase(object())
    )

    assert out["status"] == "success"
    assert ("p1", ("s1",), ("s2",)) in slice_calls
    assert ("p2", ("s5",), ("s4",)) in slice_calls
