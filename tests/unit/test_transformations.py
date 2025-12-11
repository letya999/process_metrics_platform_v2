"""Unit tests for data transformation utilities.

Tests the transformation functions in pipelines/utils/transformations.py
"""

from datetime import datetime, timezone

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

    def test_transform_basic_issue(self, sample_jira_issue):
        """Test transforming a basic issue."""
        result = transform_raw_issue_to_clean(sample_jira_issue)

        assert result["external_id"] == "10001"
        assert result["external_key"] == "PROJ-123"
        assert result["summary"] == "Test issue summary"

    def test_transform_with_integration_id(self, sample_jira_issue):
        """Test transforming issue with integration ID."""
        result = transform_raw_issue_to_clean(
            sample_jira_issue,
            integration_id="int-123",
        )

        assert result["integration_id"] == "int-123"

    def test_transform_preserves_all_fields(self, sample_jira_issue):
        """Test that all expected fields are present."""
        result = transform_raw_issue_to_clean(sample_jira_issue)

        expected_fields = [
            "external_id",
            "external_key",
            "summary",
            "description",
            "status_name",
            "status_category",
            "issue_type_name",
            "created_at",
            "updated_at",
            "resolved_at",
        ]
        for field in expected_fields:
            assert field in result


class TestTransformRawIssuesBatch:
    """Tests for transform_raw_issues_batch function."""

    def test_transform_multiple_issues(self, sample_jira_issue):
        """Test transforming multiple issues."""
        issues = [sample_jira_issue, sample_jira_issue.copy()]
        result = transform_raw_issues_batch(issues)

        assert len(result) == 2
        assert all(isinstance(item, dict) for item in result)

    def test_transform_empty_list(self):
        """Test transforming empty list."""
        result = transform_raw_issues_batch([])
        assert result == []


class TestTransformRawSprintToClean:
    """Tests for transform_raw_sprint_to_clean function."""

    def test_transform_sprint_basic(self, sample_jira_sprint):
        """Test transforming a basic sprint."""
        result = transform_raw_sprint_to_clean(sample_jira_sprint)

        assert result["external_id"] == "100"
        assert result["name"] == "Sprint 1"
        assert result["state"] == "closed"
        assert result["goal"] == "Complete initial feature set"

    def test_transform_sprint_dates(self, sample_jira_sprint):
        """Test transforming sprint dates."""
        result = transform_raw_sprint_to_clean(sample_jira_sprint)

        assert result["start_date"] is not None
        assert result["end_date"] is not None
        assert result["complete_date"] is not None

    def test_transform_sprint_with_board_id(self, sample_jira_sprint):
        """Test transforming sprint with explicit board ID."""
        result = transform_raw_sprint_to_clean(sample_jira_sprint, board_id=99)

        # Should use board_id from sprint data if present
        assert result["board_id"] == 1


class TestTransformChangelogToStatusTransitions:
    """Tests for transform_changelog_to_status_transitions function."""

    def test_transform_status_transitions(self, sample_jira_changelog):
        """Test extracting status transitions from changelog."""
        result = transform_changelog_to_status_transitions(
            issue_key="PROJ-123",
            raw_changelog=sample_jira_changelog,
        )

        assert len(result) == 2
        assert result[0]["issue_key"] == "PROJ-123"
        assert result[0]["from_status"] == "Open"
        assert result[0]["to_status"] == "In Progress"

    def test_transform_empty_changelog(self):
        """Test with empty changelog."""
        result = transform_changelog_to_status_transitions(
            issue_key="PROJ-123",
            raw_changelog={"histories": []},
        )

        assert result == []


class TestValidateCleanIssue:
    """Tests for validate_clean_issue function."""

    def test_validate_valid_issue(self, sample_clean_issue):
        """Test validating a valid issue."""
        is_valid, errors = validate_clean_issue(sample_clean_issue)

        assert is_valid is True
        assert errors == []

    def test_validate_missing_required_field(self):
        """Test validating issue with missing required field."""
        invalid_issue = {
            "external_id": "10001",
            # Missing external_key and summary
        }
        is_valid, errors = validate_clean_issue(invalid_issue)

        assert is_valid is False
        assert len(errors) >= 2

    def test_validate_invalid_date_type(self):
        """Test validating issue with invalid date type."""
        invalid_issue = {
            "external_id": "10001",
            "external_key": "PROJ-1",
            "summary": "Test",
            "created_at": "2024-01-01",  # Should be datetime, not string
        }
        is_valid, errors = validate_clean_issue(invalid_issue)

        assert is_valid is False
        assert any("datetime" in e for e in errors)

    def test_validate_invalid_story_points(self):
        """Test validating issue with invalid story points."""
        invalid_issue = {
            "external_id": "10001",
            "external_key": "PROJ-1",
            "summary": "Test",
            "story_points": "five",  # Should be numeric
        }
        is_valid, errors = validate_clean_issue(invalid_issue)

        assert is_valid is False
        assert any("story_points" in e for e in errors)


class TestDeduplicateIssues:
    """Tests for deduplicate_issues function."""

    def test_deduplicate_by_key(self):
        """Test deduplicating issues by key."""
        issues = [
            {"external_key": "PROJ-1", "summary": "First"},
            {"external_key": "PROJ-2", "summary": "Second"},
            {"external_key": "PROJ-1", "summary": "First Updated"},
        ]
        result = deduplicate_issues(issues)

        assert len(result) == 2
        keys = [i["external_key"] for i in result]
        assert "PROJ-1" in keys
        assert "PROJ-2" in keys

    def test_deduplicate_keeps_most_recent(self):
        """Test that deduplication keeps the most recent issue."""
        dt1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        dt2 = datetime(2024, 1, 15, tzinfo=timezone.utc)

        issues = [
            {"external_key": "PROJ-1", "summary": "Old", "updated_at": dt1},
            {"external_key": "PROJ-1", "summary": "New", "updated_at": dt2},
        ]
        result = deduplicate_issues(issues)

        assert len(result) == 1
        assert result[0]["summary"] == "New"

    def test_deduplicate_empty_list(self):
        """Test deduplicating empty list."""
        result = deduplicate_issues([])
        assert result == []

    def test_deduplicate_custom_key_field(self):
        """Test deduplicating with custom key field."""
        issues = [
            {"external_id": "1", "summary": "First"},
            {"external_id": "1", "summary": "Updated"},
        ]
        result = deduplicate_issues(issues, key_field="external_id")

        assert len(result) == 1


class TestEnrichIssueWithLeadTime:
    """Tests for enrich_issue_with_lead_time function."""

    def test_enrich_with_lead_time(self, sample_clean_issue):
        """Test enriching issue with lead time calculation."""
        result = enrich_issue_with_lead_time(sample_clean_issue)

        assert "lead_time_days" in result
        assert "lead_time_hours" in result
        assert result["lead_time_days"] is not None
        assert result["lead_time_days"] > 0

    def test_enrich_preserves_original_fields(self, sample_clean_issue):
        """Test that enrichment preserves all original fields."""
        result = enrich_issue_with_lead_time(sample_clean_issue)

        assert result["external_key"] == sample_clean_issue["external_key"]
        assert result["summary"] == sample_clean_issue["summary"]

    def test_enrich_unresolved_issue(self):
        """Test enriching unresolved issue (no resolved_at)."""
        issue = {
            "external_key": "PROJ-1",
            "created_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
            "resolved_at": None,
        }
        result = enrich_issue_with_lead_time(issue)

        assert result["lead_time_days"] is None
        assert result["lead_time_hours"] is None
