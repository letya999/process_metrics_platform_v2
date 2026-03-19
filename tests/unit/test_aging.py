from datetime import datetime, timedelta, timezone

import polars as pl

from pipelines.calculations import aging


def test_calculate_work_item_aging_facts_empty_issues():
    result = aging.calculate_work_item_aging_facts(
        issues_df=pl.DataFrame(),
        status_changelog_df=pl.DataFrame(),
        boards_df=pl.DataFrame(),
        board_columns_df=pl.DataFrame(),
        issue_statuses_df=pl.DataFrame(),
    )
    assert result.is_empty()
    assert "age_days" in result.columns


def test_calculate_work_item_aging_facts_all_done_returns_empty():
    issues = pl.DataFrame(
        {
            "id": ["i1"],
            "project_id": ["p1"],
            "key": ["P1-1"],
            "type_name": ["Story"],
            "status_id": ["s_done"],
            "jira_created_at": [datetime.now(timezone.utc) - timedelta(days=3)],
        }
    )
    statuses = pl.DataFrame({"id": ["s_done"], "category": ["done"], "name": ["Done"]})

    result = aging.calculate_work_item_aging_facts(
        issues_df=issues,
        status_changelog_df=pl.DataFrame(),
        boards_df=pl.DataFrame(),
        board_columns_df=pl.DataFrame(),
        issue_statuses_df=statuses,
    )
    assert result.is_empty()


def test_calculate_work_item_aging_facts_with_changelog(monkeypatch):
    now = datetime.now(timezone.utc)
    created_at = now - timedelta(days=10)
    moved_to_progress = now - timedelta(days=6)
    last_status_change = now - timedelta(days=2)

    issues = pl.DataFrame(
        {
            "id": ["i1"],
            "project_id": ["p1"],
            "key": ["P1-1"],
            "type_name": ["Story"],
            "status_id": ["s_progress"],
            "jira_created_at": [created_at],
        }
    )
    statuses = pl.DataFrame(
        {
            "id": ["s_progress"],
            "category": ["indeterminate"],
            "name": ["In Progress"],
        }
    )
    changelog = pl.DataFrame(
        {
            "issue_id": ["i1", "i1"],
            "to_status_id": ["s_progress", "s_wait"],
            "changed_at": [moved_to_progress, last_status_change],
        }
    )

    monkeypatch.setattr(
        aging,
        "identify_commitment_points",
        lambda *_args, **_kwargs: {"middle_status_ids": ["s_progress"]},
    )

    result = aging.calculate_work_item_aging_facts(
        issues_df=issues,
        status_changelog_df=changelog,
        boards_df=pl.DataFrame(),
        board_columns_df=pl.DataFrame(),
        issue_statuses_df=statuses,
    )

    assert result.height == 1
    row = result.to_dicts()[0]
    assert row["issue_id"] == "i1"
    assert row["commitment_start_at"] is not None
    assert row["age_days"] > 0
    assert row["age_in_status_days"] > 0


def test_calculate_work_item_aging_facts_without_changelog_sets_zero_status_age(
    monkeypatch,
):
    now = datetime.now(timezone.utc)
    issues = pl.DataFrame(
        {
            "id": ["i1"],
            "project_id": ["p1"],
            "key": ["P1-1"],
            "type_name": ["Story"],
            "status_id": ["s_progress"],
            "jira_created_at": [now - timedelta(days=5)],
        }
    )
    statuses = pl.DataFrame(
        {
            "id": ["s_progress"],
            "category": ["indeterminate"],
            "name": ["In Progress"],
        }
    )
    monkeypatch.setattr(
        aging,
        "identify_commitment_points",
        lambda *_args, **_kwargs: {"middle_status_ids": []},
    )

    result = aging.calculate_work_item_aging_facts(
        issues_df=issues,
        status_changelog_df=pl.DataFrame(),
        boards_df=pl.DataFrame(),
        board_columns_df=pl.DataFrame(),
        issue_statuses_df=statuses,
    )

    assert result.height == 1
    assert result["age_in_status_days"][0] == 0.0
