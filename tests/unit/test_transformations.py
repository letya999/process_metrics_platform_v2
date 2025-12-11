"""Tests for transformation utilities (raw → clean layer)."""

from datetime import datetime

import pytest

from pipelines.utils.transformations import (
    deduplicate_issues,
    enrich_issue_with_lead_time,
    transform_changelog_to_status_transitions,
    transform_raw_issue_to_clean,
    transform_raw_issues_batch,
    transform_raw_sprint_to_clean,
    validate_clean_issue,
)


class TestTransformRawIssueToClean:
    """Tests for transform_raw_issue_to_clean function."""

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
                "customfield_10016": 5,
            },
        }

    def test_transform_basic_fields(self, sample_raw_issue):
        """Test transformation of basic fields."""
        result = transform_raw_issue_to_clean(sample_raw_issue, "int-123")

        assert result["external_id"] == "10001"
        assert result["external_key"] == "PROJ-123"
        assert result["integration_id"] == "int-123"
        assert result["summary"] == "Test issue summary"

    def test_transform_status_fields(self, sample_raw_issue):
        """Test transformation of status fields."""
        result = transform_raw_issue_to_clean(sample_raw_issue)

        assert result["status_name"] == "Done"
        assert result["status_category"] == "done"

    def test_transform_dates(self, sample_raw_issue):
        """Test transformation of date fields."""
        result = transform_raw_issue_to_clean(sample_raw_issue)

        assert result["created_at"] is not None
        assert isinstance(result["created_at"], datetime)
        assert result["resolved_at"] is not None

    def test_transform_user_fields(self, sample_raw_issue):
        """Test transformation of user fields."""
        result = transform_raw_issue_to_clean(sample_raw_issue)

        assert result["assignee_account_id"] == "user-123"
        assert result["assignee_display_name"] == "John Doe"
        assert result["reporter_account_id"] == "user-456"

    def test_transform_arrays(self, sample_raw_issue):
        """Test transformation of array fields."""
        result = transform_raw_issue_to_clean(sample_raw_issue)

        assert result["labels"] == ["backend", "urgent"]
        assert result["components"] == ["API", "Database"]

    def test_transform_minimal_issue(self):
        """Test transformation of minimal issue."""
        minimal_issue = {
            "id": "10002",
            "key": "PROJ-124",
            "fields": {
                "summary": "Minimal issue",
            },
        }

        result = transform_raw_issue_to_clean(minimal_issue)

        assert result["external_id"] == "10002"
        assert result["external_key"] == "PROJ-124"
        assert result["status_name"] is None
        assert result["assignee_account_id"] is None


class TestTransformRawIssuesBatch:
    """Tests for transform_raw_issues_batch function."""

    def test_batch_transform(self):
        """Test batch transformation."""
        raw_issues = [
            {"id": "1", "key": "PROJ-1", "fields": {"summary": "Issue 1"}},
            {"id": "2", "key": "PROJ-2", "fields": {"summary": "Issue 2"}},
            {"id": "3", "key": "PROJ-3", "fields": {"summary": "Issue 3"}},
        ]

        result = transform_raw_issues_batch(raw_issues, "int-123")

        assert len(result) == 3
        assert all(r["integration_id"] == "int-123" for r in result)
        assert result[0]["external_key"] == "PROJ-1"
        assert result[1]["external_key"] == "PROJ-2"
        assert result[2]["external_key"] == "PROJ-3"

    def test_batch_transform_empty(self):
        """Test batch transformation with empty list."""
        result = transform_raw_issues_batch([])

        assert result == []


class TestTransformRawSprintToClean:
    """Tests for transform_raw_sprint_to_clean function."""

    def test_transform_active_sprint(self):
        """Test transformation of active sprint."""
        raw_sprint = {
            "id": 123,
            "name": "Sprint 5",
            "state": "active",
            "startDate": "2024-01-15T09:00:00.000Z",
            "endDate": "2024-01-29T17:00:00.000Z",
            "goal": "Complete feature X",
            "originBoardId": 10,
        }

        result = transform_raw_sprint_to_clean(raw_sprint)

        assert result["external_id"] == "123"
        assert result["name"] == "Sprint 5"
        assert result["state"] == "active"
        assert result["goal"] == "Complete feature X"
        assert result["board_id"] == 10
        assert result["start_date"] is not None
        assert result["end_date"] is not None
        assert result["complete_date"] is None

    def test_transform_closed_sprint(self):
        """Test transformation of closed sprint."""
        raw_sprint = {
            "id": 122,
            "name": "Sprint 4",
            "state": "closed",
            "startDate": "2024-01-01T09:00:00.000Z",
            "endDate": "2024-01-15T17:00:00.000Z",
            "completeDate": "2024-01-14T16:30:00.000Z",
        }

        result = transform_raw_sprint_to_clean(raw_sprint)

        assert result["state"] == "closed"
        assert result["complete_date"] is not None

    def test_transform_sprint_with_external_board_id(self):
        """Test transformation with externally provided board_id."""
        raw_sprint = {
            "id": 100,
            "name": "Sprint 1",
            "state": "future",
        }

        result = transform_raw_sprint_to_clean(raw_sprint, board_id=55)

        assert result["board_id"] == 55


class TestTransformChangelogToStatusTransitions:
    """Tests for transform_changelog_to_status_transitions function."""

    def test_extract_status_transitions(self):
        """Test extraction of status transitions."""
        raw_changelog = {
            "histories": [
                {
                    "created": "2024-01-10T10:00:00.000+0000",
                    "author": {"accountId": "user-123"},
                    "items": [
                        {
                            "field": "status",
                            "fromString": "To Do",
                            "toString": "In Progress",
                        },
                        {
                            "field": "assignee",
                            "fromString": None,
                            "toString": "John Doe",
                        },
                    ],
                },
                {
                    "created": "2024-01-14T16:00:00.000+0000",
                    "author": {"accountId": "user-123"},
                    "items": [
                        {
                            "field": "status",
                            "fromString": "In Progress",
                            "toString": "Done",
                        }
                    ],
                },
            ]
        }

        result = transform_changelog_to_status_transitions("PROJ-123", raw_changelog)

        assert len(result) == 2
        assert result[0]["issue_key"] == "PROJ-123"
        assert result[0]["from_status"] == "To Do"
        assert result[0]["to_status"] == "In Progress"
        assert result[1]["from_status"] == "In Progress"
        assert result[1]["to_status"] == "Done"

    def test_no_status_transitions(self):
        """Test when there are no status changes."""
        raw_changelog = {
            "histories": [
                {
                    "created": "2024-01-10T10:00:00.000+0000",
                    "author": {"accountId": "user-123"},
                    "items": [
                        {
                            "field": "assignee",
                            "fromString": None,
                            "toString": "John Doe",
                        }
                    ],
                }
            ]
        }

        result = transform_changelog_to_status_transitions("PROJ-123", raw_changelog)

        assert result == []


class TestValidateCleanIssue:
    """Tests for validate_clean_issue function."""

    def test_valid_issue(self):
        """Test validation of valid issue."""
        issue = {
            "external_id": "10001",
            "external_key": "PROJ-123",
            "summary": "Test issue",
            "created_at": datetime.now(),
            "story_points": 5,
        }

        is_valid, errors = validate_clean_issue(issue)

        assert is_valid is True
        assert errors == []

    def test_missing_required_fields(self):
        """Test validation with missing required fields."""
        issue = {
            "external_id": "10001",
            # missing external_key and summary
        }

        is_valid, errors = validate_clean_issue(issue)

        assert is_valid is False
        assert "Missing required field: external_key" in errors
        assert "Missing required field: summary" in errors

    def test_invalid_date_type(self):
        """Test validation with invalid date type."""
        issue = {
            "external_id": "10001",
            "external_key": "PROJ-123",
            "summary": "Test issue",
            "created_at": "2024-01-01",  # string instead of datetime
        }

        is_valid, errors = validate_clean_issue(issue)

        assert is_valid is False
        assert "created_at must be a datetime object" in errors

    def test_invalid_story_points_type(self):
        """Test validation with invalid story points type."""
        issue = {
            "external_id": "10001",
            "external_key": "PROJ-123",
            "summary": "Test issue",
            "story_points": "five",  # string instead of number
        }

        is_valid, errors = validate_clean_issue(issue)

        assert is_valid is False
        assert "story_points must be numeric" in errors

    def test_none_values_are_valid(self):
        """Test that None values for optional fields are valid."""
        issue = {
            "external_id": "10001",
            "external_key": "PROJ-123",
            "summary": "Test issue",
            "created_at": None,
            "story_points": None,
        }

        is_valid, errors = validate_clean_issue(issue)

        assert is_valid is True


class TestDeduplicateIssues:
    """Tests for deduplicate_issues function."""

    def test_deduplicate_by_key(self):
        """Test deduplication by external_key."""
        issues = [
            {
                "external_key": "PROJ-1",
                "summary": "First",
                "updated_at": datetime(2024, 1, 1),
            },
            {
                "external_key": "PROJ-1",
                "summary": "Second (newer)",
                "updated_at": datetime(2024, 1, 2),
            },
            {"external_key": "PROJ-2", "summary": "Different", "updated_at": None},
        ]

        result = deduplicate_issues(issues)

        assert len(result) == 2
        keys = [r["external_key"] for r in result]
        assert "PROJ-1" in keys
        assert "PROJ-2" in keys

        proj1 = next(r for r in result if r["external_key"] == "PROJ-1")
        assert proj1["summary"] == "Second (newer)"

    def test_deduplicate_keeps_newer(self):
        """Test that deduplication keeps the newer record."""
        issues = [
            {"external_key": "PROJ-1", "updated_at": datetime(2024, 1, 5)},
            {"external_key": "PROJ-1", "updated_at": datetime(2024, 1, 1)},
        ]

        result = deduplicate_issues(issues)

        assert len(result) == 1
        assert result[0]["updated_at"] == datetime(2024, 1, 5)

    def test_deduplicate_empty_list(self):
        """Test deduplication of empty list."""
        result = deduplicate_issues([])

        assert result == []

    def test_deduplicate_skips_missing_key(self):
        """Test that issues without key are skipped."""
        issues = [
            {"external_key": "PROJ-1", "summary": "Has key"},
            {"summary": "No key"},  # missing external_key
        ]

        result = deduplicate_issues(issues)

        assert len(result) == 1
        assert result[0]["external_key"] == "PROJ-1"


class TestEnrichIssueWithLeadTime:
    """Tests for enrich_issue_with_lead_time function."""

    def test_enrich_with_resolved_issue(self):
        """Test enrichment of resolved issue."""
        issue = {
            "external_key": "PROJ-1",
            "created_at": datetime(2024, 1, 1, 10, 0, 0),
            "resolved_at": datetime(2024, 1, 3, 10, 0, 0),
        }

        result = enrich_issue_with_lead_time(issue)

        assert result["lead_time_days"] == 2.0
        assert result["lead_time_hours"] == 48.0
        # Original fields preserved
        assert result["external_key"] == "PROJ-1"
        assert result["created_at"] == issue["created_at"]

    def test_enrich_unresolved_issue(self):
        """Test enrichment of unresolved issue."""
        issue = {
            "external_key": "PROJ-1",
            "created_at": datetime(2024, 1, 1, 10, 0, 0),
            "resolved_at": None,
        }

        result = enrich_issue_with_lead_time(issue)

        assert result["lead_time_days"] is None
        assert result["lead_time_hours"] is None

    def test_enrich_missing_dates(self):
        """Test enrichment with missing dates."""
        issue = {
            "external_key": "PROJ-1",
        }

        result = enrich_issue_with_lead_time(issue)

        assert result["lead_time_days"] is None
        assert result["lead_time_hours"] is None
