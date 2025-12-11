"""Tests for Jira parsing utilities."""

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

    def test_parse_none_returns_none(self):
        """Test that None input returns None."""
        assert parse_jira_datetime(None) is None

    def test_parse_empty_string_returns_none(self):
        """Test that empty string returns None."""
        assert parse_jira_datetime("") is None

    def test_parse_standard_jira_format(self):
        """Test parsing standard Jira datetime format."""
        result = parse_jira_datetime("2024-01-15T10:30:00.000+0000")
        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 10
        assert result.minute == 30

    def test_parse_jira_format_with_timezone(self):
        """Test parsing Jira datetime with different timezone."""
        result = parse_jira_datetime("2024-06-20T14:45:30.123+0300")
        assert result is not None
        assert result.year == 2024
        assert result.month == 6
        assert result.day == 20

    def test_parse_iso_format_with_z(self):
        """Test parsing ISO format with Z timezone."""
        result = parse_jira_datetime("2024-03-10T08:00:00.000Z")
        assert result is not None
        assert result.year == 2024
        assert result.month == 3
        assert result.day == 10

    def test_parse_without_timezone(self):
        """Test parsing datetime without timezone."""
        result = parse_jira_datetime("2024-01-01T12:00:00.000")
        assert result is not None
        assert result.year == 2024

    def test_parse_invalid_format_returns_none(self):
        """Test that invalid format returns None."""
        assert parse_jira_datetime("invalid-date") is None
        assert parse_jira_datetime("2024/01/01") is None


class TestParseJiraIssue:
    """Tests for parse_jira_issue function."""

    @pytest.fixture
    def sample_raw_issue(self):
        """Sample raw Jira issue data."""
        return {
            "id": "10001",
            "key": "PROJ-123",
            "fields": {
                "summary": "Test issue summary",
                "description": "Test description",
                "status": {
                    "name": "Done",
                    "statusCategory": {"key": "done"},
                },
                "issuetype": {
                    "id": "10002",
                    "name": "Story",
                },
                "priority": {"name": "High"},
                "project": {
                    "id": "10000",
                    "key": "PROJ",
                    "name": "Test Project",
                },
                "created": "2024-01-01T10:00:00.000+0000",
                "updated": "2024-01-15T14:30:00.000+0000",
                "resolutiondate": "2024-01-14T16:00:00.000+0000",
                "assignee": {
                    "accountId": "user-123",
                    "displayName": "John Doe",
                },
                "reporter": {
                    "accountId": "user-456",
                    "displayName": "Jane Smith",
                },
                "labels": ["backend", "urgent"],
                "components": [{"name": "API"}, {"name": "Database"}],
                "customfield_10016": 5,  # Story points
            },
        }

    def test_parse_basic_fields(self, sample_raw_issue):
        """Test parsing basic issue fields."""
        result = parse_jira_issue(sample_raw_issue)

        assert result["external_id"] == "10001"
        assert result["external_key"] == "PROJ-123"
        assert result["summary"] == "Test issue summary"
        assert result["description"] == "Test description"

    def test_parse_status(self, sample_raw_issue):
        """Test parsing status fields."""
        result = parse_jira_issue(sample_raw_issue)

        assert result["status_name"] == "Done"
        assert result["status_category"] == "done"

    def test_parse_issue_type(self, sample_raw_issue):
        """Test parsing issue type fields."""
        result = parse_jira_issue(sample_raw_issue)

        assert result["issue_type_name"] == "Story"
        assert result["issue_type_id"] == "10002"

    def test_parse_project(self, sample_raw_issue):
        """Test parsing project fields."""
        result = parse_jira_issue(sample_raw_issue)

        assert result["project_key"] == "PROJ"
        assert result["project_id"] == "10000"
        assert result["project_name"] == "Test Project"

    def test_parse_dates(self, sample_raw_issue):
        """Test parsing date fields."""
        result = parse_jira_issue(sample_raw_issue)

        assert result["created_at"] is not None
        assert result["created_at"].year == 2024
        assert result["created_at"].month == 1
        assert result["created_at"].day == 1

        assert result["resolved_at"] is not None
        assert result["resolved_at"].day == 14

    def test_parse_assignee_reporter(self, sample_raw_issue):
        """Test parsing assignee and reporter."""
        result = parse_jira_issue(sample_raw_issue)

        assert result["assignee_account_id"] == "user-123"
        assert result["assignee_display_name"] == "John Doe"
        assert result["reporter_account_id"] == "user-456"
        assert result["reporter_display_name"] == "Jane Smith"

    def test_parse_story_points(self, sample_raw_issue):
        """Test parsing story points."""
        result = parse_jira_issue(sample_raw_issue)

        assert result["story_points"] == 5

    def test_parse_labels_and_components(self, sample_raw_issue):
        """Test parsing labels and components."""
        result = parse_jira_issue(sample_raw_issue)

        assert result["labels"] == ["backend", "urgent"]
        assert result["components"] == ["API", "Database"]

    def test_parse_minimal_issue(self):
        """Test parsing issue with minimal fields."""
        minimal_issue = {
            "id": "10002",
            "key": "PROJ-124",
            "fields": {
                "summary": "Minimal issue",
            },
        }

        result = parse_jira_issue(minimal_issue)

        assert result["external_id"] == "10002"
        assert result["external_key"] == "PROJ-124"
        assert result["summary"] == "Minimal issue"
        assert result["status_name"] is None
        assert result["assignee_account_id"] is None

    def test_parse_issue_with_sprint(self):
        """Test parsing issue with sprint field."""
        issue_with_sprint = {
            "id": "10003",
            "key": "PROJ-125",
            "fields": {
                "summary": "Issue with sprint",
                "customfield_10020": [
                    {"id": 1, "name": "Sprint 1"},
                    {"id": 2, "name": "Sprint 2"},
                ],
            },
        }

        result = parse_jira_issue(issue_with_sprint)

        # Should get the last (active) sprint
        assert result["sprint_id"] == 2
        assert result["sprint_name"] == "Sprint 2"


class TestParseJiraSprint:
    """Tests for parse_jira_sprint function."""

    def test_parse_active_sprint(self):
        """Test parsing active sprint."""
        raw_sprint = {
            "id": 123,
            "name": "Sprint 5",
            "state": "active",
            "startDate": "2024-01-15T09:00:00.000Z",
            "endDate": "2024-01-29T17:00:00.000Z",
            "goal": "Complete feature X",
            "originBoardId": 10,
        }

        result = parse_jira_sprint(raw_sprint)

        assert result["external_id"] == "123"
        assert result["name"] == "Sprint 5"
        assert result["state"] == "active"
        assert result["start_date"] is not None
        assert result["end_date"] is not None
        assert result["complete_date"] is None
        assert result["goal"] == "Complete feature X"
        assert result["board_id"] == 10

    def test_parse_closed_sprint(self):
        """Test parsing closed sprint."""
        raw_sprint = {
            "id": 122,
            "name": "Sprint 4",
            "state": "closed",
            "startDate": "2024-01-01T09:00:00.000Z",
            "endDate": "2024-01-15T17:00:00.000Z",
            "completeDate": "2024-01-14T16:30:00.000Z",
        }

        result = parse_jira_sprint(raw_sprint)

        assert result["state"] == "closed"
        assert result["complete_date"] is not None


class TestParseJiraChangelog:
    """Tests for parse_jira_changelog function."""

    def test_parse_changelog_with_status_change(self):
        """Test parsing changelog with status changes."""
        raw_changelog = {
            "histories": [
                {
                    "created": "2024-01-10T10:00:00.000+0000",
                    "author": {"accountId": "user-123"},
                    "items": [
                        {
                            "field": "status",
                            "fieldtype": "jira",
                            "fromString": "To Do",
                            "toString": "In Progress",
                            "from": "1",
                            "to": "2",
                        }
                    ],
                },
                {
                    "created": "2024-01-14T16:00:00.000+0000",
                    "author": {"accountId": "user-123"},
                    "items": [
                        {
                            "field": "status",
                            "fieldtype": "jira",
                            "fromString": "In Progress",
                            "toString": "Done",
                            "from": "2",
                            "to": "3",
                        }
                    ],
                },
            ]
        }

        result = parse_jira_changelog(raw_changelog)

        assert len(result) == 2
        assert result[0]["field"] == "status"
        assert result[0]["from_value"] == "To Do"
        assert result[0]["to_value"] == "In Progress"
        assert result[1]["to_value"] == "Done"

    def test_parse_changelog_multiple_items_per_history(self):
        """Test parsing changelog with multiple items per history."""
        raw_changelog = {
            "histories": [
                {
                    "created": "2024-01-10T10:00:00.000+0000",
                    "author": {"accountId": "user-123"},
                    "items": [
                        {
                            "field": "status",
                            "fieldtype": "jira",
                            "fromString": "To Do",
                            "toString": "In Progress",
                        },
                        {
                            "field": "assignee",
                            "fieldtype": "jira",
                            "fromString": None,
                            "toString": "John Doe",
                        },
                    ],
                }
            ]
        }

        result = parse_jira_changelog(raw_changelog)

        assert len(result) == 2
        assert result[0]["field"] == "status"
        assert result[1]["field"] == "assignee"

    def test_parse_empty_changelog(self):
        """Test parsing empty changelog."""
        result = parse_jira_changelog({"histories": []})
        assert result == []

        result = parse_jira_changelog({})
        assert result == []


class TestExtractStatusChanges:
    """Tests for extract_status_changes function."""

    def test_extract_status_changes(self):
        """Test extracting only status changes."""
        changelog_items = [
            {"field": "status", "to_value": "In Progress"},
            {"field": "assignee", "to_value": "John Doe"},
            {"field": "status", "to_value": "Done"},
            {"field": "priority", "to_value": "High"},
        ]

        result = extract_status_changes(changelog_items)

        assert len(result) == 2
        assert all(item["field"] == "status" for item in result)

    def test_extract_no_status_changes(self):
        """Test extraction when no status changes exist."""
        changelog_items = [
            {"field": "assignee", "to_value": "John Doe"},
            {"field": "priority", "to_value": "High"},
        ]

        result = extract_status_changes(changelog_items)
        assert result == []
