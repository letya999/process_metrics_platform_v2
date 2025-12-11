"""Unit tests for Jira data parsing utilities.

Tests the parsing functions in pipelines/utils/__init__.py
"""

from datetime import datetime, timezone

import pytest

from pipelines.utils import (
    extract_status_changes,
    parse_jira_changelog,
    parse_jira_datetime,
    parse_jira_issue,
    parse_jira_sprint,
)


class TestParseJiraDatetime:
    """Tests for parse_jira_datetime function."""

    def test_parse_datetime_with_timezone(self):
        """Test parsing Jira datetime with timezone offset."""
        dt_str = "2024-01-15T10:30:00.000+0000"
        result = parse_jira_datetime(dt_str)

        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 10
        assert result.minute == 30

    def test_parse_datetime_with_z_suffix(self):
        """Test parsing datetime with Z suffix (UTC)."""
        dt_str = "2024-01-15T10:30:00.000Z"
        result = parse_jira_datetime(dt_str)

        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_parse_datetime_without_milliseconds(self):
        """Test parsing datetime without milliseconds."""
        dt_str = "2024-01-15T10:30:00+0000"
        result = parse_jira_datetime(dt_str)

        assert result is not None
        assert result.year == 2024

    def test_parse_none_returns_none(self):
        """Test that None input returns None."""
        result = parse_jira_datetime(None)
        assert result is None

    def test_parse_empty_string_returns_none(self):
        """Test that empty string returns None."""
        result = parse_jira_datetime("")
        assert result is None

    def test_parse_invalid_format_returns_none(self):
        """Test that invalid format returns None."""
        result = parse_jira_datetime("not-a-date")
        assert result is None


class TestParseJiraIssue:
    """Tests for parse_jira_issue function."""

    def test_parse_issue_basic_fields(self, sample_jira_issue):
        """Test parsing basic issue fields."""
        result = parse_jira_issue(sample_jira_issue)

        assert result["external_id"] == "10001"
        assert result["external_key"] == "PROJ-123"
        assert result["summary"] == "Test issue summary"
        assert result["description"] == "Test issue description"

    def test_parse_issue_status(self, sample_jira_issue):
        """Test parsing issue status fields."""
        result = parse_jira_issue(sample_jira_issue)

        assert result["status_name"] == "Done"
        assert result["status_category"] == "done"

    def test_parse_issue_type(self, sample_jira_issue):
        """Test parsing issue type fields."""
        result = parse_jira_issue(sample_jira_issue)

        assert result["issue_type_name"] == "Story"
        assert result["issue_type_id"] == "10002"

    def test_parse_issue_project(self, sample_jira_issue):
        """Test parsing project fields."""
        result = parse_jira_issue(sample_jira_issue)

        assert result["project_key"] == "PROJ"
        assert result["project_id"] == "10000"
        assert result["project_name"] == "Test Project"

    def test_parse_issue_dates(self, sample_jira_issue):
        """Test parsing date fields."""
        result = parse_jira_issue(sample_jira_issue)

        assert result["created_at"] is not None
        assert result["updated_at"] is not None
        assert result["resolved_at"] is not None
        assert isinstance(result["created_at"], datetime)

    def test_parse_issue_assignee(self, sample_jira_issue):
        """Test parsing assignee fields."""
        result = parse_jira_issue(sample_jira_issue)

        assert result["assignee_account_id"] == "user123"
        assert result["assignee_display_name"] == "John Doe"

    def test_parse_issue_reporter(self, sample_jira_issue):
        """Test parsing reporter fields."""
        result = parse_jira_issue(sample_jira_issue)

        assert result["reporter_account_id"] == "user456"
        assert result["reporter_display_name"] == "Jane Smith"

    def test_parse_issue_story_points(self, sample_jira_issue):
        """Test parsing story points custom field."""
        result = parse_jira_issue(sample_jira_issue)

        assert result["story_points"] == 5

    def test_parse_issue_sprint(self, sample_jira_issue):
        """Test parsing sprint custom field."""
        result = parse_jira_issue(sample_jira_issue)

        assert result["sprint_id"] == 100
        assert result["sprint_name"] == "Sprint 1"

    def test_parse_issue_labels(self, sample_jira_issue):
        """Test parsing labels."""
        result = parse_jira_issue(sample_jira_issue)

        assert result["labels"] == ["backend", "feature"]

    def test_parse_issue_components(self, sample_jira_issue):
        """Test parsing components."""
        result = parse_jira_issue(sample_jira_issue)

        assert result["components"] == ["API", "Database"]

    def test_parse_issue_empty_fields(self):
        """Test parsing issue with minimal/empty fields."""
        minimal_issue = {
            "id": "10001",
            "key": "PROJ-1",
            "fields": {
                "summary": "Minimal issue",
            },
        }
        result = parse_jira_issue(minimal_issue)

        assert result["external_id"] == "10001"
        assert result["external_key"] == "PROJ-1"
        assert result["summary"] == "Minimal issue"
        assert result["assignee_account_id"] is None
        assert result["story_points"] is None


class TestParseJiraSprint:
    """Tests for parse_jira_sprint function."""

    def test_parse_sprint_basic_fields(self, sample_jira_sprint):
        """Test parsing basic sprint fields."""
        result = parse_jira_sprint(sample_jira_sprint)

        assert result["external_id"] == "100"
        assert result["name"] == "Sprint 1"
        assert result["state"] == "closed"
        assert result["goal"] == "Complete initial feature set"

    def test_parse_sprint_dates(self, sample_jira_sprint):
        """Test parsing sprint date fields."""
        result = parse_jira_sprint(sample_jira_sprint)

        assert result["start_date"] is not None
        assert result["end_date"] is not None
        assert result["complete_date"] is not None
        assert isinstance(result["start_date"], datetime)

    def test_parse_sprint_board_id(self, sample_jira_sprint):
        """Test parsing board ID."""
        result = parse_jira_sprint(sample_jira_sprint)

        assert result["board_id"] == 1


class TestParseJiraChangelog:
    """Tests for parse_jira_changelog function."""

    def test_parse_changelog_items(self, sample_jira_changelog):
        """Test parsing changelog items."""
        result = parse_jira_changelog(sample_jira_changelog)

        assert len(result) == 2
        assert result[0]["field"] == "status"
        assert result[0]["from_value"] == "Open"
        assert result[0]["to_value"] == "In Progress"

    def test_parse_changelog_author(self, sample_jira_changelog):
        """Test parsing changelog author."""
        result = parse_jira_changelog(sample_jira_changelog)

        assert result[0]["author_account_id"] == "user123"

    def test_parse_changelog_dates(self, sample_jira_changelog):
        """Test parsing changelog dates."""
        result = parse_jira_changelog(sample_jira_changelog)

        assert result[0]["changed_at"] is not None
        assert isinstance(result[0]["changed_at"], datetime)

    def test_parse_empty_changelog(self):
        """Test parsing empty changelog."""
        result = parse_jira_changelog({"histories": []})
        assert result == []


class TestExtractStatusChanges:
    """Tests for extract_status_changes function."""

    def test_extract_status_changes(self, sample_jira_changelog):
        """Test extracting only status changes from changelog."""
        changelog_items = parse_jira_changelog(sample_jira_changelog)
        result = extract_status_changes(changelog_items)

        assert len(result) == 2
        assert all(item["field"] == "status" for item in result)

    def test_extract_status_changes_filters_other_fields(self):
        """Test that non-status changes are filtered out."""
        changelog_items = [
            {"field": "status", "from_value": "Open", "to_value": "Done"},
            {"field": "assignee", "from_value": "User A", "to_value": "User B"},
            {"field": "priority", "from_value": "Low", "to_value": "High"},
        ]
        result = extract_status_changes(changelog_items)

        assert len(result) == 1
        assert result[0]["field"] == "status"
