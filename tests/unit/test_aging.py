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
            "from_status_id": [None, "s_progress"],
            "to_status_id": ["s_progress", "s_wait"],
            "changed_at": [moved_to_progress, last_status_change],
        }
    )

    monkeypatch.setattr(
        aging,
        "identify_commitment_points_heuristic",
        lambda *_args, **_kwargs: {
            "start_status_ids": ["s_progress"],
            "middle_status_ids": ["s_progress"],
            "end_status_ids": [],
            "commitment_rule_id": None,
        },
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
        "identify_commitment_points_heuristic",
        lambda *_args, **_kwargs: {
            "start_status_ids": [],
            "middle_status_ids": [],
            "end_status_ids": [],
            "commitment_rule_id": None,
        },
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


def test_calculate_work_item_aging_facts_resolves_commitment_per_project_board(
    monkeypatch,
):
    now = datetime.now(timezone.utc)
    issues = pl.DataFrame(
        {
            "id": ["i1", "i2"],
            "project_id": ["p1", "p2"],
            "key": ["P1-1", "P2-1"],
            "type_name": ["Story", "Story"],
            "status_id": ["s_active", "s_active"],
            "jira_created_at": [now - timedelta(days=20), now - timedelta(days=20)],
        }
    )
    statuses = pl.DataFrame(
        {
            "id": ["s_active"],
            "category": ["indeterminate"],
            "name": ["In Progress"],
        }
    )
    boards = pl.DataFrame(
        {"id": ["b1", "b2"], "project_id": ["p1", "p2"], "name": ["B1", "B2"]}
    )
    board_columns = pl.DataFrame(
        {
            "id": ["c1", "c2"],
            "board_id": ["b1", "b2"],
            "name": ["In Progress", "In Progress"],
            "position": [1, 1],
            "status_id": ["s_mid_p1", "s_mid_p2"],
        }
    )
    changelog = pl.DataFrame(
        {
            "issue_id": ["i1", "i2"],
            "from_status_id": [None, None],
            "to_status_id": ["s_mid_p1", "s_mid_p2"],
            "changed_at": [now - timedelta(days=7), now - timedelta(days=4)],
        }
    )

    def _heuristic(df, *_args, **_kwargs):
        # Deliberately choose only the first status in passed df.
        # If calculation uses full cross-project df, issue i2 will miss start event.
        status_id = df["status_id"][0] if not df.is_empty() else None
        return {
            "start_status_ids": [status_id] if status_id else [],
            "middle_status_ids": [status_id] if status_id else [],
            "end_status_ids": [],
            "commitment_rule_id": None,
        }

    monkeypatch.setattr(aging, "identify_commitment_points_heuristic", _heuristic)

    result = aging.calculate_work_item_aging_facts(
        issues_df=issues,
        status_changelog_df=changelog,
        boards_df=boards,
        board_columns_df=board_columns,
        issue_statuses_df=statuses,
    )

    assert result.height == 2
    rows = {row["issue_id"]: row for row in result.to_dicts()}
    assert rows["i1"]["commitment_start_at"] == now - timedelta(days=7)
    assert rows["i2"]["commitment_start_at"] == now - timedelta(days=4)
