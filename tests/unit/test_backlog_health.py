"""
Unit tests for Backlog Health metrics calculation.
"""

from datetime import datetime, timedelta, timezone

import polars as pl

from pipelines.calculations.backlog_health import (
    calculate_backlog_distribution,
    calculate_backlog_health,
)


class TestBacklogHealth:
    """Tests for calculate_backlog_health."""

    def test_calculate_backlog_health_timezone_compatibility(self):
        """
        Verify that using UTC-aware datetimes in input data does not cause
        PanicException when comparing with strict types in Polars.
        This tests the fix for 'failed to determine supertype of datetime[μs] and datetime[ns, UTC]'.
        """
        # UTC-aware dates
        now = datetime.now(timezone.utc)
        created_at_utc = now - timedelta(days=10)
        updated_at_utc = now - timedelta(days=5)

        issues = pl.DataFrame(
            {
                "id": ["ISS-1"],
                "project_id": ["PROJ-1"],
                "status_id": ["STATUS-1"],
                "type_id": ["TYPE-1"],
                "jira_created_at": [created_at_utc],
                "jira_updated_at": [updated_at_utc],
            }
        )

        issue_statuses = pl.DataFrame(
            {
                "id": ["STATUS-1"],
                "project_id": ["PROJ-1"],
                "name": ["To Do"],
                "category": ["to_do"],
            }
        )

        # Empty field dfs for this test
        field_values = pl.DataFrame(
            {
                "issue_id": [],
                "field_key_id": [],
                "value": [],
                "json_value": [],
                "updated_at": [],
            },
            schema={
                "issue_id": pl.Utf8,
                "field_key_id": pl.Utf8,
                "value": pl.Utf8,
                "json_value": pl.Utf8,
                "updated_at": pl.Datetime,
            },
        )
        field_keys = pl.DataFrame(
            {
                "id": [],
                "project_id": [],
                "external_key": [],
                "name": [],
                "is_custom": [],
                "created_at": [],
            },
            schema={
                "id": pl.Utf8,
                "project_id": pl.Utf8,
                "external_key": pl.Utf8,
                "name": pl.Utf8,
                "is_custom": pl.Boolean,
                "created_at": pl.Datetime,
            },
        )

        # This should not raise PanicException
        result = calculate_backlog_health(
            issues_df=issues,
            issue_statuses_df=issue_statuses,
            field_values_df=field_values,
            field_keys_df=field_keys,
            stale_threshold_days=30,
        )

        assert not result.is_empty()
        assert result["total_backlog_size"][0] == 1
        assert result["avg_age_days"][0] >= 9.9  # Approx 10 days
        assert result["stale_issues_count"][0] == 0

    def test_calculate_backlog_health_stale_issues(self):
        """Verify stale issues categorization."""
        now = datetime.now(timezone.utc)

        # Issue 1: Updated recently (Not Stale)
        # Issue 2: Updated 40 days ago (Stale)
        issues = pl.DataFrame(
            {
                "id": ["ISS-1", "ISS-2"],
                "project_id": ["PROJ-1", "PROJ-1"],
                "status_id": ["STATUS-1", "STATUS-1"],
                "type_id": ["TYPE-1", "TYPE-1"],
                "jira_created_at": [now - timedelta(days=50), now - timedelta(days=60)],
                "jira_updated_at": [now - timedelta(days=2), now - timedelta(days=40)],
            }
        )

        issue_statuses = pl.DataFrame(
            {
                "id": ["STATUS-1"],
                "project_id": ["PROJ-1"],
                "name": ["To Do"],
                "category": ["to_do"],
            }
        )

        field_values = pl.DataFrame(
            {"issue_id": [], "field_key_id": [], "value": [], "json_value": []}
        )
        field_keys = pl.DataFrame({"id": [], "project_id": [], "name": []})

        result = calculate_backlog_health(
            issues_df=issues,
            issue_statuses_df=issue_statuses,
            field_values_df=field_values,
            field_keys_df=field_keys,
            stale_threshold_days=30,
        )

        assert result["total_backlog_size"][0] == 2
        assert result["stale_issues_count"][0] == 1
        assert result["stale_percentage"][0] == 50.0

    def test_calculate_backlog_distribution_attribute_error_fix(self):
        """
        Verify that accessing priority field ID uses index access [0] instead of .first()
        to prevent AttributeError: 'Series' object has no attribute 'first'.
        """
        issues = pl.DataFrame(
            {
                "id": ["ISS-1"],
                "project_id": ["PROJ-1"],
                "status_id": ["S1"],
                "type_id": ["T1"],
            }
        )
        statuses = pl.DataFrame({"id": ["S1"], "category": ["todo"]})
        types = pl.DataFrame({"id": ["T1"], "name": ["Bug"]})

        # Mock field_keys returning a match for 'priority'
        field_keys = pl.DataFrame(
            {"id": ["FIELD-1"], "name": ["Priority"], "project_id": ["PROJ-1"]}
        )

        field_values = pl.DataFrame(
            {
                "issue_id": ["ISS-1"],
                "field_key_id": ["FIELD-1"],
                "json_value": ['{"name": "High"}'],
            }
        )

        # This calls the function that had the .first() error
        result = calculate_backlog_distribution(
            issues, statuses, types, field_values, field_keys
        )

        assert not result.is_empty()
        assert result["priority"][0] == "High"
