"""
Unit tests for Throughput calculation logic.
"""

from datetime import date, datetime

import polars as pl

from pipelines.calculations.throughput import (
    calculate_weekly_throughput,
)


class TestThroughput:
    """Tests for calculate_weekly_throughput."""

    def test_calculate_throughput_basic(self):
        """Test basic weekly aggregation."""
        # 2 issues completed in Week 1 (Jan 1-7 2024)
        # 1 issue completed in Week 2 (Jan 8-14 2024)

        issues = pl.DataFrame(
            {
                "id": ["1", "2", "3"],
                "project_id": ["P1"] * 3,
                "key": ["K1", "K2", "K3"],
                "type_name": ["Task"] * 3,
                "jira_created_at": [datetime(2023, 12, 1)] * 3,
                "jira_resolved_at": [
                    datetime(2024, 1, 2),  # Tue Week 1
                    datetime(2024, 1, 3),  # Wed Week 1
                    datetime(2024, 1, 9),  # Tue Week 2
                ],
            }
        )

        # Determine Done from Resolved Date (no board config)
        result = calculate_weekly_throughput(
            issues, pl.DataFrame({}), pl.DataFrame({}), pl.DataFrame({})
        )

        week1 = result.filter(pl.col("week_start_date") == date(2024, 1, 1))
        week2 = result.filter(pl.col("week_start_date") == date(2024, 1, 8))

        assert week1["issues_completed"][0] == 2
        assert week2["issues_completed"][0] == 1

    def test_calculate_throughput_changelog_source(self):
        """Test throughput using changelog Done date."""
        # Issue resolved in field on Jan 10, but moved to Done column on Jan 5 (Week 1)
        # Should count in Week 1.

        issues = pl.DataFrame(
            {
                "id": ["1"],
                "project_id": ["P1"],
                "key": ["K1"],
                "type_name": ["Task"],
                "jira_created_at": [datetime(2023, 12, 1)],
                "jira_resolved_at": [datetime(2024, 1, 10)],
            }
        )

        changelog = pl.DataFrame(
            {
                "issue_id": ["1"],
                "to_status_id": ["STATUS-DONE"],
                "changed_at": [datetime(2024, 1, 5)],  # Fri Week 1
            }
        )

        board_columns = pl.DataFrame({"status_id": ["STATUS-DONE"], "name": ["Done"]})

        result = calculate_weekly_throughput(
            issues, changelog, pl.DataFrame({}), board_columns
        )

        assert result["issues_completed"][0] == 1
        assert result["week_start_date"][0] == date(
            2024, 1, 1
        )  # Jan 1 is Mon of that week

    def test_throughput_empty(self):
        """Test empty input."""
        result = calculate_weekly_throughput(
            pl.DataFrame({}), pl.DataFrame({}), pl.DataFrame({}), pl.DataFrame({})
        )

        assert result.is_empty()
        assert "issues_completed" in result.columns
