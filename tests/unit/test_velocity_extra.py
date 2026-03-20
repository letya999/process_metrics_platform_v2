from datetime import date, datetime

import polars as pl

from pipelines.calculations import velocity


def test_identify_sprint_final_scope_uses_changelog_plus_fallback_and_filters_subtasks():
    sprint_issues = pl.DataFrame(
        {
            "issue_id": ["i1", "i2", "i3"],
            "sprint_id": ["s1", "s1", "s1"],
        }
    )
    sprint_changelog = pl.DataFrame(
        {
            "issue_id": ["i1", "i1", "i2"],
            "sprint_id": ["s1", "s1", "s1"],
            "action": ["added", "removed", "added"],
            "changed_at": [
                datetime(2026, 1, 1),
                datetime(2026, 1, 3),
                datetime(2026, 1, 2),
            ],
        }
    )
    issues = pl.DataFrame(
        {
            "id": ["i1", "i2", "i3"],
            "type_name": ["Story", "Task", "Sub-task"],
        }
    )

    result = velocity.identify_sprint_final_scope(
        sprint_issues, sprint_changelog, issues
    )
    tuples = set((r["issue_id"], r["sprint_id"]) for r in result.to_dicts())
    assert ("i2", "s1") in tuples
    assert ("i1", "s1") not in tuples
    assert ("i3", "s1") not in tuples


def test_determine_story_points_at_date_prefers_historic_value_after_target_date():
    scope = pl.DataFrame({"issue_id": ["i1"], "sprint_id": ["s1"]})
    sprints = pl.DataFrame({"id": ["s1"], "start_date": [datetime(2026, 1, 5)]})
    current_sp = pl.DataFrame({"issue_id": ["i1"], "story_points": [8.0]})
    changelog = pl.DataFrame(
        {
            "issue_id": ["i1"],
            "field_key_id": ["f1"],
            "old_value": ["3"],
            "changed_at": [datetime(2026, 1, 6)],
        }
    )
    field_keys = pl.DataFrame(
        {"id": ["f1"], "external_key": ["customfield_10036"], "name": ["Story Points"]}
    )

    result = velocity.determine_story_points_at_date(
        scope, sprints, current_sp, changelog, field_keys, date_col="start_date"
    )
    assert result["story_points"][0] == 3.0


def test_identify_completed_issues_uses_from_status_of_first_future_change():
    scope = pl.DataFrame({"issue_id": ["i1"], "sprint_id": ["s1"]})
    # jira_resolved_at inside window provides completion evidence required by
    # the window-gate check; the future-change path confirms status was "done".
    issues = pl.DataFrame(
        {
            "id": ["i1"],
            "status_id": ["todo"],
            "jira_resolved_at": [datetime(2026, 1, 8)],
        }
    )
    sprints = pl.DataFrame(
        {
            "id": ["s1"],
            "start_date": [datetime(2026, 1, 1)],
            "end_date": [datetime(2026, 1, 10)],
            "complete_date": [None],
        }
    )
    # Only change is AFTER sprint end — exercises the first-future-change path
    status_changelog = pl.DataFrame(
        {
            "issue_id": ["i1"],
            "from_status_id": ["done"],
            "to_status_id": ["todo"],
            "changed_at": [datetime(2026, 1, 11)],
        }
    )

    result = velocity.identify_completed_issues(
        scope_df=scope,
        issues_df=issues,
        status_changelog_df=status_changelog,
        done_status_ids=["done"],
        sprints_df=sprints,
    )

    assert result.height == 1
    assert result["is_completed"][0] is True


def test_calculate_velocity_facts_orchestrates_with_stubbed_components(monkeypatch):
    monkeypatch.setattr(
        velocity, "get_done_status_ids", lambda *_args, **_kwargs: ["done"]
    )
    monkeypatch.setattr(
        velocity,
        "extract_story_points",
        lambda *_args, **_kwargs: pl.DataFrame(
            {"issue_id": ["i1"], "story_points": [5.0]}
        ),
    )
    monkeypatch.setattr(
        velocity,
        "identify_sprint_commitment",
        lambda *_args, **_kwargs: pl.DataFrame(
            {"issue_id": ["i1"], "sprint_id": ["s1"]}
        ),
    )
    monkeypatch.setattr(
        velocity,
        "identify_sprint_final_scope",
        lambda *_args, **_kwargs: pl.DataFrame(
            {"issue_id": ["i1"], "sprint_id": ["s1"]}
        ),
    )
    monkeypatch.setattr(
        velocity,
        "identify_completed_issues",
        lambda *_args, **_kwargs: pl.DataFrame(
            {"issue_id": ["i1"], "sprint_id": ["s1"], "is_completed": [True]}
        ),
    )
    monkeypatch.setattr(
        velocity,
        "determine_story_points_at_date",
        lambda scope_df, *_args, **_kwargs: scope_df.with_columns(
            pl.lit(5.0).alias("story_points")
        ),
    )

    sprints = pl.DataFrame(
        {
            "id": ["s1"],
            "project_id": ["p1"],
            "name": ["Sprint 1"],
            "start_date": [date(2026, 1, 1)],
            "end_date": [date(2026, 1, 14)],
            "complete_date": [None],
        }
    )

    result = velocity.calculate_velocity_facts(
        sprints_df=sprints,
        sprint_issues_df=pl.DataFrame({"issue_id": ["i1"], "sprint_id": ["s1"]}),
        sprint_changelog_df=pl.DataFrame(),
        issues_df=pl.DataFrame(
            {"id": ["i1"], "type_name": ["Story"], "status_id": ["done"]}
        ),
        field_values_df=pl.DataFrame(),
        field_keys_df=pl.DataFrame(),
        status_changelog_df=pl.DataFrame(),
        boards_df=pl.DataFrame(),
        board_columns_df=pl.DataFrame(),
        field_value_changelog_df=pl.DataFrame(),
        issue_statuses_df=pl.DataFrame(),
    )

    assert result.height == 1
    row = result.to_dicts()[0]
    assert row["planned_story_points"] == 5.0
    assert row["completed_story_points"] == 5.0
    assert row["planned_issues"] == 1
    assert row["completed_issues"] == 1


def test_calculate_velocity_facts_keeps_same_name_sprints_separate(monkeypatch):
    monkeypatch.setattr(
        velocity, "get_done_status_ids", lambda *_args, **_kwargs: ["done"]
    )
    monkeypatch.setattr(
        velocity,
        "extract_story_points",
        lambda *_args, **_kwargs: pl.DataFrame(
            {"issue_id": ["i1", "i2"], "story_points": [5.0, 8.0]}
        ),
    )
    monkeypatch.setattr(
        velocity,
        "identify_sprint_commitment",
        lambda *_args, **_kwargs: pl.DataFrame(
            {"issue_id": ["i1", "i2"], "sprint_id": ["s1", "s2"]}
        ),
    )
    monkeypatch.setattr(
        velocity,
        "identify_sprint_final_scope",
        lambda *_args, **_kwargs: pl.DataFrame(
            {"issue_id": ["i1", "i2"], "sprint_id": ["s1", "s2"]}
        ),
    )
    monkeypatch.setattr(
        velocity,
        "identify_completed_issues",
        lambda *_args, **_kwargs: pl.DataFrame(
            {
                "issue_id": ["i1", "i2"],
                "sprint_id": ["s1", "s2"],
                "is_completed": [True, True],
            }
        ),
    )
    monkeypatch.setattr(
        velocity,
        "determine_story_points_at_date",
        lambda scope_df, _sprints_df, current_sp_df, *_args, **_kwargs: scope_df.join(
            current_sp_df, on="issue_id", how="left"
        ),
    )

    sprints = pl.DataFrame(
        {
            "id": ["s1", "s2"],
            "project_id": ["p1", "p1"],
            "name": ["Sprint Shared Name", "Sprint Shared Name"],
            "start_date": [date(2026, 1, 1), date(2026, 1, 15)],
            "end_date": [date(2026, 1, 14), date(2026, 1, 28)],
            "complete_date": [None, None],
        }
    )

    result = velocity.calculate_velocity_facts(
        sprints_df=sprints,
        sprint_issues_df=pl.DataFrame(
            {"issue_id": ["i1", "i2"], "sprint_id": ["s1", "s2"]}
        ),
        sprint_changelog_df=pl.DataFrame(),
        issues_df=pl.DataFrame(
            {
                "id": ["i1", "i2"],
                "type_name": ["Story", "Story"],
                "status_id": ["done", "done"],
            }
        ),
        field_values_df=pl.DataFrame(),
        field_keys_df=pl.DataFrame(),
        status_changelog_df=pl.DataFrame(),
        boards_df=pl.DataFrame(),
        board_columns_df=pl.DataFrame(),
        field_value_changelog_df=pl.DataFrame(),
        issue_statuses_df=pl.DataFrame(),
    )

    assert result.height == 2
    rows = sorted(result.to_dicts(), key=lambda x: x["iteration_id"])
    assert rows[0]["iteration_id"] == "s1"
    assert rows[0]["planned_story_points"] == 5.0
    assert rows[1]["iteration_id"] == "s2"
    assert rows[1]["planned_story_points"] == 8.0


def test_calculate_velocity_slice_by_issue_type_uses_commitment_for_plan(monkeypatch):
    captured_scope_issue_sets = []

    monkeypatch.setattr(
        velocity, "get_done_status_ids", lambda *_args, **_kwargs: ["done"]
    )
    monkeypatch.setattr(
        velocity,
        "extract_story_points",
        lambda *_args, **_kwargs: pl.DataFrame(
            {"issue_id": ["i-commit", "i-final"], "story_points": [3.0, 5.0]}
        ),
    )
    monkeypatch.setattr(
        velocity,
        "identify_sprint_commitment",
        lambda *_args, **_kwargs: pl.DataFrame(
            {"issue_id": ["i-commit"], "sprint_id": ["s1"]}
        ),
    )
    monkeypatch.setattr(
        velocity,
        "identify_sprint_final_scope",
        lambda *_args, **_kwargs: pl.DataFrame(
            {"issue_id": ["i-final"], "sprint_id": ["s1"]}
        ),
    )
    monkeypatch.setattr(
        velocity,
        "identify_completed_issues",
        lambda *_args, **_kwargs: pl.DataFrame(
            {"issue_id": ["i-final"], "sprint_id": ["s1"], "is_completed": [True]}
        ),
    )

    def _determine_story_points_at_date(
        scope_df, _sprints_df, current_sp_df, *_args, **_kwargs
    ):
        captured_scope_issue_sets.append(
            sorted(scope_df["issue_id"].cast(pl.Utf8).to_list())
        )
        return scope_df.join(current_sp_df, on="issue_id", how="left")

    monkeypatch.setattr(
        velocity, "determine_story_points_at_date", _determine_story_points_at_date
    )

    result = velocity.calculate_velocity_slice_by_issue_type(
        sprint_issues_df=pl.DataFrame(
            {"issue_id": ["i-commit", "i-final"], "sprint_id": ["s1", "s1"]}
        ),
        sprint_changelog_df=pl.DataFrame(),
        issues_df=pl.DataFrame(
            {
                "id": ["i-commit", "i-final"],
                "type_name": ["Story", "Bug"],
                "status_id": ["todo", "done"],
            }
        ),
        sprints_df=pl.DataFrame(
            {
                "id": ["s1"],
                "project_id": ["p1"],
                "name": ["Sprint 1"],
                "start_date": [date(2026, 1, 1)],
                "end_date": [date(2026, 1, 14)],
                "complete_date": [None],
            }
        ),
        field_values_df=pl.DataFrame(),
        field_keys_df=pl.DataFrame(),
        status_changelog_df=pl.DataFrame(),
        boards_df=pl.DataFrame(),
        board_columns_df=pl.DataFrame(),
        field_value_changelog_df=pl.DataFrame(),
        issue_statuses_df=pl.DataFrame(),
    )

    assert result.height >= 1
    # First call is plan path, second call is completed path.
    assert captured_scope_issue_sets[0] == ["i-commit"]
    assert captured_scope_issue_sets[1] == ["i-final"]
