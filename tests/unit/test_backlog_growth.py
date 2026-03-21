"""
Unit tests for Backlog Health metrics calculation.
"""

from datetime import datetime, timedelta, timezone

import polars as pl

from pipelines.calculations.backlog_growth import (
    _calculate_issue_status_on_dates,
    calculate_age_distribution,
    calculate_backlog_distribution,
    calculate_backlog_growth_trends,
)
from pipelines.calculations.backlog_growth import (
    calculate_backlog_growth as calculate_backlog_health,
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
                "jira_resolved_at": [None],
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
            days_back=0,
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
                "jira_resolved_at": [None, None],
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
            days_back=0,
        )

        assert result["total_backlog_size"][0] == 2
        assert result["stale_issues_count"][0] == 1
        assert result["stale_percentage"][0] == 50.0

    def test_calculate_backlog_distribution(self):
        """Test backlog distribution by priority."""
        issues = pl.DataFrame(
            {
                "id": ["I1"],
                "project_id": ["P1"],
                "status_id": ["S1"],
                "type_id": ["T1"],
            }
        )
        statuses = pl.DataFrame({"id": ["S1"], "category": ["todo"]})
        types = pl.DataFrame({"id": ["T1"], "name": ["Bug"]})

        # Priority Field
        field_keys = pl.DataFrame(
            {"id": ["F1"], "name": ["Priority"], "project_id": ["P1"]}
        )
        field_values = pl.DataFrame(
            {
                "issue_id": ["I1"],
                "field_key_id": ["F1"],
                "json_value": ['{"name": "High"}'],
            }
        )

        result = calculate_backlog_distribution(
            issues, statuses, types, field_values, field_keys
        )

        assert result["priority"][0] == "High"
        assert result["issue_count"][0] == 1

    def test_calculate_backlog_growth_trends(self):
        """Test backlog growth trends (Created vs Completed)."""
        # Week 1: Mon Jan 1
        d1 = datetime(2024, 1, 1, 10, 0, 0)
        # Week 2: Mon Jan 8
        d2 = datetime(2024, 1, 8, 10, 0, 0)

        issues = pl.DataFrame(
            {
                "project_id": ["P1", "P1", "P1"],
                "jira_created_at": [d1, d1, d2],
                "jira_resolved_at": [None, d1, d2],
            }
        )

        # d1: Created 2, Completed 1 -> Net +1
        # d2: Created 1, Completed 1 -> Net 0

        result = calculate_backlog_growth_trends(
            issues,
            pl.DataFrame(
                {}
            ),  # Statuses not used for basic created/resolved check in current impl
            period="weekly",
        )

        assert result.height == 2

        # Check first week
        w1 = result.filter(pl.col("period_start") == d1.date())
        assert w1["created_count"][0] == 2
        assert w1["completed_count"][0] == 1
        assert w1["net_growth"][0] == 1

        # Check second week
        w2 = result.filter(pl.col("period_start") == d2.date())
        assert w2["created_count"][0] == 1
        assert w2["completed_count"][0] == 1
        assert w2["net_growth"][0] == 0

    def test_calculate_issue_status_on_dates_empty(self):
        result = _calculate_issue_status_on_dates(
            pl.DataFrame(), pl.DataFrame(), pl.DataFrame()
        )
        assert result.is_empty()
        assert "issue_id" in result.columns

    def test_calculate_issue_status_on_dates_without_changelog(self):
        issues = pl.DataFrame(
            {
                "id": ["I1"],
                "project_id": ["P1"],
                "status_id": ["S1"],
                "jira_created_at": [datetime(2024, 1, 1)],
                "jira_updated_at": [datetime(2024, 1, 2)],
            }
        )
        date_range = pl.DataFrame({"date": [datetime(2024, 1, 1).date()]})

        result = _calculate_issue_status_on_dates(issues, pl.DataFrame(), date_range)

        assert result.height == 1
        assert result["status_id"][0] == "S1"
        assert result["last_status_change_at"][0] is None

    def test_calculate_backlog_growth_with_backlog_enter_exit_counts(self):
        fact_date = datetime(2024, 1, 2, tzinfo=timezone.utc)
        issues = pl.DataFrame(
            {
                "id": ["I1"],
                "project_id": ["P1"],
                "status_id": ["S_DONE"],
                "type_id": ["T1"],
                "jira_created_at": [datetime(2024, 1, 1, tzinfo=timezone.utc)],
                "jira_updated_at": [datetime(2024, 1, 2, tzinfo=timezone.utc)],
                "jira_resolved_at": [datetime(2024, 1, 2, tzinfo=timezone.utc)],
            }
        )
        issue_statuses = pl.DataFrame(
            {
                "id": ["S_BACKLOG", "S_DONE"],
                "project_id": ["P1", "P1"],
                "name": ["Backlog", "Done"],
                "category": ["to_do", "done"],
            }
        )
        changelog = pl.DataFrame(
            {
                "issue_id": ["I1", "I1"],
                "from_status_id": [None, "S_BACKLOG"],
                "to_status_id": ["S_BACKLOG", "S_DONE"],
                "changed_at": [
                    datetime(2024, 1, 1, tzinfo=timezone.utc),
                    datetime(2024, 1, 2, tzinfo=timezone.utc),
                ],
            }
        )
        board_statuses = pl.DataFrame(
            {"project_id": ["P1"], "position": [0], "status_id": ["S_BACKLOG"]}
        )

        result = calculate_backlog_health(
            issues_df=issues,
            issue_statuses_df=issue_statuses,
            field_values_df=pl.DataFrame(
                {"issue_id": [], "field_key_id": [], "json_value": []}
            ),
            field_keys_df=pl.DataFrame({"id": [], "name": []}),
            changelog_df=changelog,
            board_column_statuses_df=board_statuses,
            fact_date=fact_date,
            days_back=1,
            stale_threshold_days=30,
        )

        assert not result.is_empty()
        assert "entered_backlog_count" in result.columns
        assert "exited_backlog_count" in result.columns
        assert result["entered_backlog_count"].sum() >= 1
        assert result["exited_backlog_count"].sum() >= 1

    def test_calculate_age_distribution_buckets(self):
        now = datetime.now(timezone.utc)
        issues = pl.DataFrame(
            {
                "id": ["I1", "I2", "I3", "I4"],
                "project_id": ["P1", "P1", "P1", "P1"],
                "status_id": ["S1", "S1", "S1", "S1"],
                "jira_created_at": [
                    now - timedelta(days=3),
                    now - timedelta(days=15),
                    now - timedelta(days=60),
                    now - timedelta(days=120),
                ],
            }
        )
        statuses = pl.DataFrame({"id": ["S1"], "category": ["to_do"]})

        result = calculate_age_distribution(issues, statuses)

        assert result.height == 4
        assert result["issue_count"].sum() == 4


def test_calculate_backlog_growth_empty():
    """Test backlog growth calculation with empty issues."""
    issues = pl.DataFrame(
        schema={
            "id": pl.Utf8,
            "project_id": pl.Utf8,
            "status_id": pl.Utf8,
            "jira_created_at": pl.Datetime,
        }
    )
    statuses = pl.DataFrame({"id": ["1"], "category": ["todo"]})
    fields = pl.DataFrame()
    keys = pl.DataFrame()

    result = calculate_backlog_health(issues, statuses, fields, keys)
    assert result.is_empty()
    assert "total_backlog_size" in result.columns


def test_calculate_backlog_growth_trends_empty():
    """Test backlog growth trends with empty issues."""
    issues = pl.DataFrame(
        schema={
            "id": pl.Utf8,
            "project_id": pl.Utf8,
            "status_id": pl.Utf8,
            "jira_created_at": pl.Datetime,
        }
    )
    statuses = pl.DataFrame({"id": ["1"], "category": ["todo"]})

    result = calculate_backlog_growth_trends(issues, statuses)
    assert result.is_empty()
    assert "net_growth" in result.columns


def test_calculate_backlog_distribution_priority_extraction():
    """Test priority extraction from JSON field values in backlog distribution."""
    issues = pl.DataFrame(
        {"id": ["I1"], "project_id": ["P1"], "status_id": ["S1"], "type_id": ["T1"]}
    )
    statuses = pl.DataFrame({"id": ["S1"], "category": ["todo"]})
    types = pl.DataFrame({"id": ["T1"], "name": ["Story"]})
    keys = pl.DataFrame({"id": ["K1"], "name": ["Priority"]})
    values = pl.DataFrame(
        {"issue_id": ["I1"], "field_key_id": ["K1"], "json_value": ['{"name": "High"}']}
    )

    result = calculate_backlog_distribution(issues, statuses, types, values, keys)
    assert not result.is_empty()
    assert result.filter(pl.col("priority") == "High").height == 1


def test_calculate_backlog_distribution_empty():
    """Test backlog distribution with empty issues."""
    issues = pl.DataFrame(
        schema={
            "id": pl.Utf8,
            "project_id": pl.Utf8,
            "status_id": pl.Utf8,
            "type_id": pl.Utf8,
        }
    )
    statuses = pl.DataFrame()
    types = pl.DataFrame()
    values = pl.DataFrame()
    keys = pl.DataFrame()

    result = calculate_backlog_distribution(issues, statuses, types, values, keys)
    assert result.is_empty()


def test_calculate_age_distribution_empty():
    """Test age distribution with empty issues."""
    issues = pl.DataFrame(
        schema={"id": pl.Utf8, "project_id": pl.Utf8, "status_id": pl.Utf8}
    )
    statuses = pl.DataFrame()

    result = calculate_age_distribution(issues, statuses)
    assert result.is_empty()


def test_calculate_issue_status_on_dates_internal():
    """Test the internal helper for status tracking on dates."""
    from datetime import date

    issues = pl.DataFrame(
        {
            "id": ["I1"],
            "project_id": ["P1"],
            "status_id": ["S1"],
            "jira_created_at": [datetime(2025, 1, 1)],
        }
    )
    changelog = pl.DataFrame(
        {
            "issue_id": ["I1"],
            "to_status_id": ["S2"],
            "changed_at": [datetime(2025, 1, 3)],
        }
    )
    dates = pl.DataFrame(
        {
            "fact_date": [
                date(2025, 1, 1),
                date(2025, 1, 2),
                date(2025, 1, 3),
                date(2025, 1, 4),
            ]
        }
    )

    result = _calculate_issue_status_on_dates(issues, changelog, dates)
    assert result.height == 4
    # On Jan 1, date should be date(2025, 1, 1)
    assert result.filter(pl.col("date") == date(2025, 1, 1))["status_id"][0] == "S1"
    # On Jan 3, status should be S2
    assert result.filter(pl.col("date") == date(2025, 1, 3))["status_id"][0] == "S2"
