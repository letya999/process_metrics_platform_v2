"""
Unit tests for Velocity metrics calculation logic (Polars implementation)

These tests verify the business rules for determining:
- Which issues are "Planned" at sprint start
- Which issues are "Completed" by sprint end
- Story Points extraction and aggregation
"""

from datetime import date, datetime

import polars as pl

from pipelines.calculations.velocity import (
    extract_story_points,
    get_done_status_ids,
    identify_completed_issues,
    identify_sprint_commitment,
)


class TestPlannedIssues:
    """Tests for identifying planned issues."""

    def test_issue_added_before_start_is_planned(self):
        """Test that issue added BEFORE sprint start is marked as planned."""
        sprint_issues = pl.DataFrame({"issue_id": ["ISS-1"], "sprint_id": ["SPRINT-1"]})

        sprint_changelog = pl.DataFrame(
            {
                "issue_id": ["ISS-1"],
                "sprint_id": ["SPRINT-1"],
                "action": ["added"],
                "changed_at": [datetime(2024, 1, 1, 8, 0)],
            }
        )

        issues = pl.DataFrame(
            {
                "id": ["ISS-1"],
                "jira_created_at": [datetime(2023, 12, 1)],
                "type_name": ["Task"],
            }
        )

        sprints = pl.DataFrame(
            {
                "id": ["SPRINT-1"],
                "start_date": [date(2024, 1, 2)],
                "end_date": [date(2024, 1, 15)],
            }
        )

        result = identify_sprint_commitment(
            sprint_changelog, sprints, issues, sprint_issues
        )

        assert result.filter(pl.col("issue_id") == "ISS-1").height > 0

    def test_issue_added_mid_sprint_is_planned_scope_creep(self):
        """Test that issue added AFTER sprint start IS planned (scope creep) if present at end."""
        sprint_issues = pl.DataFrame({"issue_id": ["ISS-2"], "sprint_id": ["SPRINT-1"]})

        sprint_changelog = pl.DataFrame(
            {
                "issue_id": ["ISS-2"],
                "sprint_id": ["SPRINT-1"],
                "action": ["added"],
                "changed_at": [datetime(2024, 1, 5, 10, 0)],  # Added mid-sprint
            }
        )

        issues = pl.DataFrame(
            {
                "id": ["ISS-2"],
                "jira_created_at": [datetime(2024, 1, 3)],
                "type_name": ["Task"],
            }
        )

        sprints = pl.DataFrame(
            {
                "id": ["SPRINT-1"],
                "start_date": [date(2024, 1, 2)],
                "end_date": [date(2024, 1, 15)],
            }
        )

        result = identify_sprint_commitment(
            sprint_changelog, sprints, issues, sprint_issues
        )

        # Issue added mid-sprint is NOT planned (it is scope creep), so not in commitment
        assert result.filter(pl.col("issue_id") == "ISS-2").height == 0

    def test_issue_created_before_start_with_no_history_is_planned(self):
        """Issue created before sprint start with no changelog = planned."""
        sprint_issues = pl.DataFrame({"issue_id": ["ISS-3"], "sprint_id": ["SPRINT-1"]})

        # Empty changelog (no history)
        sprint_changelog = pl.DataFrame(
            {"issue_id": [], "sprint_id": [], "action": [], "changed_at": []},
            schema={
                "issue_id": pl.Utf8,
                "sprint_id": pl.Utf8,
                "action": pl.Utf8,
                "changed_at": pl.Datetime,
            },
        )

        issues = pl.DataFrame(
            {
                "id": ["ISS-3"],
                "jira_created_at": [datetime(2023, 12, 1)],  # Created before sprint
                "type_name": ["Task"],
            }
        )

        sprints = pl.DataFrame(
            {
                "id": ["SPRINT-1"],
                "start_date": [date(2024, 1, 2)],
                "end_date": [date(2024, 1, 15)],
            }
        )

        result = identify_sprint_commitment(
            sprint_changelog, sprints, issues, sprint_issues
        )

        assert result.filter(pl.col("issue_id") == "ISS-3").height > 0


class TestCompletedIssues:
    """Tests for identifying completed issues."""

    def test_resolved_issue_is_completed(self):
        """Issue resolved before sprint end = completed."""
        planned = pl.DataFrame({"issue_id": ["ISS-1"], "sprint_id": ["SPRINT-1"]})

        issues = pl.DataFrame(
            {
                "id": ["ISS-1"],
                "jira_resolved_at": [datetime(2024, 1, 10)],  # Resolved during sprint
                "status_id": ["STATUS-DONE"],
            }
        )

        status_changelog = pl.DataFrame(
            {
                "issue_id": ["ISS-1"],
                "from_status_id": ["status-todo"],
                "to_status_id": ["status-done"],
                "changed_at": [datetime(2024, 1, 10)],
            }
        )

        sprints = pl.DataFrame(
            {
                "id": ["SPRINT-1"],
                "end_date": [date(2024, 1, 15)],
                "start_date": [date(2024, 1, 1)],
                "complete_date": [None],
            }
        )

        result = identify_completed_issues(
            planned,
            issues,
            status_changelog,
            done_status_ids=["status-done"],
            sprints_df=sprints,
        )

        assert len(result) == 1
        assert result["is_completed"][0] is True

    def test_resolved_after_sprint_end_is_not_completed(self):
        """Issue resolved AFTER sprint end = NOT completed."""
        planned = pl.DataFrame({"issue_id": ["ISS-2"], "sprint_id": ["SPRINT-1"]})

        issues = pl.DataFrame(
            {
                "id": ["ISS-2"],
                "jira_resolved_at": [datetime(2024, 1, 20)],  # Resolved AFTER end
                "status_id": ["STATUS-DONE"],
            }
        )

        status_changelog = pl.DataFrame(
            {
                "issue_id": ["ISS-2"],
                "from_status_id": ["status-todo"],
                "to_status_id": ["status-done"],
                "changed_at": [datetime(2024, 1, 20)],
            }
        )

        sprints = pl.DataFrame(
            {
                "id": ["SPRINT-1"],
                "end_date": [date(2024, 1, 15)],
                "start_date": [date(2024, 1, 1)],
                "complete_date": [None],
            }
        )

        result = identify_completed_issues(
            planned,
            issues,
            status_changelog,
            done_status_ids=["status-done"],
            sprints_df=sprints,
        )

        assert len(result) == 0  # Not completed

    def test_done_status_transition_marks_completed(self):
        """Issue transitioned to Done status before end = completed."""
        planned = pl.DataFrame({"issue_id": ["ISS-3"], "sprint_id": ["SPRINT-1"]})

        issues = pl.DataFrame(
            {
                "id": ["ISS-3"],
                "jira_resolved_at": [None],  # Not resolved via field
                "status_id": ["STATUS-TODO"],
            }
        )

        status_changelog = pl.DataFrame(
            {
                "issue_id": ["ISS-3"],
                "to_status_id": ["STATUS-DONE"],
                "changed_at": [datetime(2024, 1, 12)],
            }
        )

        sprints = pl.DataFrame(
            {
                "id": ["SPRINT-1"],
                "end_date": [date(2024, 1, 15)],
                "start_date": [date(2024, 1, 1)],
                "complete_date": [None],
            }
        )

        result = identify_completed_issues(
            planned,
            issues,
            status_changelog,
            done_status_ids=["status-done"],
            sprints_df=sprints,
        )

        assert len(result) == 1
        assert result["is_completed"][0] is True


class TestStoryPoints:
    """Tests for story points extraction."""

    def test_extract_story_points_from_field(self):
        """Story points extracted from custom field."""
        planned = pl.DataFrame({"id": ["ISS-1"], "sprint_id": ["SPRINT-1"]})

        field_values = pl.DataFrame(
            {"issue_id": ["ISS-1"], "field_key_id": ["FIELD-1"], "json_value": ["5"]}
        )

        field_keys = pl.DataFrame(
            {
                "id": ["FIELD-1"],
                "external_key": ["customfield_10036"],
                "name": ["Story Points"],
            }
        )

        result = extract_story_points(
            planned,
            field_values_df=field_values,
            field_keys_df=field_keys,
        )

        assert result.filter(pl.col("issue_id") == "ISS-1")["story_points"][0] == 5.0

    def test_missing_story_points_defaults_to_zero(self):
        """Issue without story points = 0."""
        planned = pl.DataFrame({"id": ["ISS-2"], "sprint_id": ["SPRINT-1"]})

        field_values = pl.DataFrame(
            {"issue_id": [], "field_key_id": [], "json_value": []},
            schema={
                "issue_id": pl.Utf8,
                "field_key_id": pl.Utf8,
                "json_value": pl.Utf8,
            },
        )

        field_keys = pl.DataFrame(
            {
                "id": ["FIELD-1"],
                "external_key": ["customfield_10036"],
                "name": ["Story Points"],
            }
        )

        result = extract_story_points(
            planned,
            field_values_df=field_values,
            field_keys_df=field_keys,
        )

        assert result.filter(pl.col("issue_id") == "ISS-2")["story_points"][0] == 0.0


class TestDoneStatusIdentification:
    """Tests for identifying Done statuses from board columns."""

    def test_identify_done_statuses(self):
        """Done statuses identified from board columns."""
        boards = pl.DataFrame({"id": ["BOARD-1"], "project_id": ["PROJ-1"]})

        board_columns = pl.DataFrame(
            {
                "id": ["COL-1", "COL-2", "COL-3"],
                "board_id": ["BOARD-1", "BOARD-1", "BOARD-1"],
                "name": ["To Do", "In Progress", "Done"],
                "status_id": ["STATUS-1", "STATUS-2", "STATUS-3"],
            }
        )

        result = get_done_status_ids(boards, board_columns)

        assert "status-3" in result
        assert "status-1" not in result

    def test_empty_board_columns_returns_empty_list(self):
        """No board columns = no Done statuses."""
        boards = pl.DataFrame({"id": [], "project_id": []})
        board_columns = pl.DataFrame(
            {"id": [], "board_id": [], "name": [], "status_id": []},
            schema={
                "id": pl.Utf8,
                "board_id": pl.Utf8,
                "name": pl.Utf8,
                "status_id": pl.Utf8,
            },
        )

        result = get_done_status_ids(boards, board_columns)

        assert result == []

    def test_identify_done_statuses_by_position(self):
        """Done statuses identified as right-most column by position."""
        boards = pl.DataFrame({"id": ["BOARD-1"]})
        board_columns = pl.DataFrame(
            {
                "board_id": ["BOARD-1", "BOARD-1", "BOARD-1"],
                "position": [0, 1, 2],
                "status_id": ["S1", "S2", "S3"],
            }
        )
        result = get_done_status_ids(boards, board_columns)
        assert "s3" in result
        assert "s1" not in result
        assert "s2" not in result

    def test_identify_done_statuses_fallback_to_category(self):
        """Done statuses fallback to status category when board mapping is missing."""
        boards = pl.DataFrame()
        board_columns = pl.DataFrame()
        issue_statuses = pl.DataFrame(
            {"id": ["S1", "S2"], "category": ["to_do", "done"]}
        )
        result = get_done_status_ids(boards, board_columns, issue_statuses)
        assert "s2" in result
        assert "s1" not in result
