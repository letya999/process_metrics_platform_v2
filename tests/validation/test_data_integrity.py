"""Data validation tests for data integrity.

These tests verify data integrity constraints:
- FK relationships are valid
- NULL constraints are enforced
- Materialized views are correctly structured
"""

from datetime import datetime
from pathlib import Path

from pipelines.utils import parse_jira_sprint
from pipelines.utils.transformations import (
    deduplicate_issues,
    transform_raw_issue_to_clean,
    validate_clean_issue,
)


class TestIssueDataIntegrity:
    """Tests for issue data integrity."""

    def test_required_fields_not_null(self):
        """Test that required fields are not null after transformation."""
        raw_issue = {
            "id": "10001",
            "key": "PROJ-123",
            "fields": {
                "summary": "Test issue",
            },
        }

        clean = transform_raw_issue_to_clean(raw_issue)

        # Required fields should always be present
        assert clean["external_id"] is not None
        assert clean["external_key"] is not None
        assert clean["summary"] is not None

    def test_external_id_format(self):
        """Test external_id is always a string."""
        raw_issues = [
            {"id": "10001", "key": "P-1", "fields": {"summary": "A"}},
            {"id": 10002, "key": "P-2", "fields": {"summary": "B"}},  # int id
            {"id": "abc-123", "key": "P-3", "fields": {"summary": "C"}},
        ]

        for raw in raw_issues:
            clean = transform_raw_issue_to_clean(raw)
            assert isinstance(clean["external_id"], str)

    def test_external_key_uniqueness(self):
        """Test that deduplication maintains uniqueness by key."""
        dt1 = datetime(2024, 1, 1)
        dt2 = datetime(2024, 1, 2)
        issues = [
            {"external_key": "PROJ-1", "summary": "First", "updated_at": dt1},
            {"external_key": "PROJ-1", "summary": "Duplicate", "updated_at": dt2},
            {"external_key": "PROJ-2", "summary": "Different", "updated_at": dt1},
        ]

        deduped = deduplicate_issues(issues)
        keys = [i["external_key"] for i in deduped]

        assert len(keys) == len(set(keys)), "Keys should be unique after deduplication"

    def test_date_fields_are_datetime_or_none(self):
        """Test date fields are proper datetime objects or None."""
        raw_issue = {
            "id": "10001",
            "key": "PROJ-123",
            "fields": {
                "summary": "Test",
                "created": "2024-01-01T10:00:00.000+0000",
                "updated": "2024-01-02T10:00:00.000+0000",
                "resolutiondate": "2024-01-03T10:00:00.000+0000",
            },
        }

        clean = transform_raw_issue_to_clean(raw_issue)

        assert isinstance(clean["created_at"], datetime)
        assert isinstance(clean["updated_at"], datetime)
        assert isinstance(clean["resolved_at"], datetime)

    def test_null_dates_are_none(self):
        """Test that missing dates are None, not empty strings."""
        raw_issue = {
            "id": "10001",
            "key": "PROJ-123",
            "fields": {
                "summary": "Test",
                # No date fields
            },
        }

        clean = transform_raw_issue_to_clean(raw_issue)

        assert clean["created_at"] is None
        assert clean["resolved_at"] is None


class TestSprintDataIntegrity:
    """Tests for sprint data integrity."""

    def test_sprint_external_id_is_string(self):
        """Test sprint external_id is converted to string."""
        raw_sprints = [
            {"id": 123, "name": "Sprint 1", "state": "active"},
            {"id": "456", "name": "Sprint 2", "state": "closed"},
        ]

        for raw in raw_sprints:
            parsed = parse_jira_sprint(raw)
            assert isinstance(parsed["external_id"], str)

    def test_sprint_state_values(self):
        """Test sprint state is one of expected values."""
        valid_states = ["future", "active", "closed"]
        raw_sprints = [
            {"id": 1, "name": "Sprint", "state": state} for state in valid_states
        ]

        for raw, expected_state in zip(raw_sprints, valid_states, strict=True):
            parsed = parse_jira_sprint(raw)
            assert parsed["state"] == expected_state

    def test_sprint_dates_consistency(self):
        """Test sprint dates are logically consistent."""
        raw_sprint = {
            "id": 100,
            "name": "Sprint X",
            "state": "closed",
            "startDate": "2024-01-01T00:00:00.000Z",
            "endDate": "2024-01-15T00:00:00.000Z",
            "completeDate": "2024-01-14T00:00:00.000Z",
        }

        parsed = parse_jira_sprint(raw_sprint)

        # Complete date should be before or equal to end date
        if parsed["complete_date"] and parsed["end_date"]:
            assert parsed["complete_date"] <= parsed["end_date"]

        # Start date should be before end date
        if parsed["start_date"] and parsed["end_date"]:
            assert parsed["start_date"] < parsed["end_date"]


class TestValidationFunction:
    """Tests for the validate_clean_issue function."""

    def test_valid_issue_passes(self):
        """Test that valid issues pass validation."""
        valid_issue = {
            "external_id": "10001",
            "external_key": "PROJ-123",
            "summary": "Valid issue",
            "created_at": datetime.now(),
            "story_points": 5,
        }

        is_valid, errors = validate_clean_issue(valid_issue)

        assert is_valid is True
        assert errors == []

    def test_missing_required_field_fails(self):
        """Test that missing required fields fail validation."""
        invalid_issue = {
            "external_id": "10001",
            # missing external_key
            # missing summary
        }

        is_valid, errors = validate_clean_issue(invalid_issue)

        assert is_valid is False
        assert len(errors) == 2

    def test_wrong_type_fails(self):
        """Test that wrong types fail validation."""
        invalid_issue = {
            "external_id": "10001",
            "external_key": "PROJ-123",
            "summary": "Test",
            "created_at": "2024-01-01",  # string instead of datetime
            "story_points": "five",  # string instead of number
        }

        is_valid, errors = validate_clean_issue(invalid_issue)

        assert is_valid is False
        assert len(errors) == 2


class TestForeignKeyConstraints:
    """Tests for FK relationship constraints (conceptual)."""

    def test_project_references_in_issues(self):
        """Test that issue project references are consistent."""
        raw_issue = {
            "id": "10001",
            "key": "PROJ-123",
            "fields": {
                "summary": "Test",
                "project": {
                    "id": "10000",
                    "key": "PROJ",
                    "name": "Test Project",
                },
            },
        }

        clean = transform_raw_issue_to_clean(raw_issue)

        # Project key in issue should match project data
        assert clean["project_external_key"] == "PROJ"
        assert clean["external_key"].startswith("PROJ-")

    def test_integration_id_propagation(self):
        """Test that integration_id is propagated correctly."""
        raw_issue = {
            "id": "10001",
            "key": "PROJ-123",
            "fields": {"summary": "Test"},
        }

        integration_id = "int-uuid-123"
        clean = transform_raw_issue_to_clean(raw_issue, integration_id=integration_id)

        assert clean["integration_id"] == integration_id


class TestMetricsViewStructure:
    """Tests for metrics view SQL structure."""

    def test_lead_time_view_exists(self):
        """Verify lead time view SQL file exists with required columns."""
        project_root = Path(__file__).parent.parent.parent
        metrics_sql = project_root / "db" / "views" / "metrics.sql"

        content = metrics_sql.read_text()

        # Check for required columns in mv_lead_time
        assert "mv_lead_time" in content
        assert "lead_time_days" in content
        assert "lead_time_hours" in content
        assert "issue_key" in content

    def test_velocity_view_exists(self):
        """Verify velocity view SQL file has required columns."""
        project_root = Path(__file__).parent.parent.parent
        metrics_sql = project_root / "db" / "views" / "metrics.sql"

        content = metrics_sql.read_text()

        # Check for required columns in mv_velocity
        assert "mv_velocity" in content
        assert "sprint_id" in content
        assert "completion_rate" in content.lower() or "completed_issues" in content

    def test_throughput_view_exists(self):
        """Verify throughput view SQL file has required columns."""
        project_root = Path(__file__).parent.parent.parent
        metrics_sql = project_root / "db" / "views" / "metrics.sql"

        content = metrics_sql.read_text()

        # Check for required columns in mv_throughput
        assert "mv_throughput" in content
        assert "resolved_date" in content or "issues_completed" in content

    def test_refresh_function_exists(self):
        """Verify refresh function is defined."""
        project_root = Path(__file__).parent.parent.parent
        metrics_sql = project_root / "db" / "views" / "metrics.sql"

        content = metrics_sql.read_text()

        assert "refresh_all_views" in content


class TestSchemaFiles:
    """Tests for schema file integrity."""

    def test_platform_schema_exists(self):
        """Verify platform schema SQL exists."""
        project_root = Path(__file__).parent.parent.parent
        schema_file = project_root / "db" / "schemas" / "platform_schema.sql"

        assert schema_file.exists()
        content = schema_file.read_text()
        assert "platform" in content.lower()

    def test_clean_jira_schema_exists(self):
        """Verify clean_jira schema SQL exists."""
        project_root = Path(__file__).parent.parent.parent
        schema_file = project_root / "db" / "schemas" / "clean_jira_schema.sql"

        assert schema_file.exists()
        content = schema_file.read_text()
        assert "clean_jira" in content

    def test_bi_analytics_schema_exists(self):
        """Verify bi_analytics schema SQL exists."""
        project_root = Path(__file__).parent.parent.parent
        schema_file = project_root / "db" / "schemas" / "bi_analytics_schema.sql"

        assert schema_file.exists()
