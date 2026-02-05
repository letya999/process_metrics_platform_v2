"""
Unit tests for Time to Market (TTM) calculation logic.
"""

from datetime import datetime, timezone

import polars as pl

from pipelines.calculations.time_to_market import (
    calculate_time_to_market,
)


class TestTimeToMarket:
    """Tests for calculate_time_to_market."""

    def test_filter_high_level_items(self):
        """Test that only Epics/Stories/Features are included."""
        issues = pl.DataFrame(
            {
                "id": ["E1", "S1", "T1", "B1"],
                "key": ["K1", "K2", "K3", "K4"],
                "project_id": ["P1"] * 4,
                "type_id": ["TYPE-EPIC", "TYPE-STORY", "TYPE-TASK", "TYPE-BUG"],
                "jira_created_at": [datetime(2024, 1, 1)] * 4,
                "jira_resolved_at": [datetime(2024, 1, 10)] * 4,
            }
        )

        issue_types = pl.DataFrame(
            {
                "id": ["TYPE-EPIC", "TYPE-STORY", "TYPE-TASK", "TYPE-BUG"],
                "name": ["Epic", "Story", "Task", "Bug"],
                "hierarchy_level": ["epic", "story", "task", "task"],
            }
        )

        # Empty support tables
        releases = pl.DataFrame(
            {"id": [], "release_date": []},
            schema={"id": pl.Utf8, "release_date": pl.Datetime},
        )
        fix_versions = pl.DataFrame(
            {"issue_id": [], "version_id": []},
            schema={"issue_id": pl.Utf8, "version_id": pl.Utf8},
        )
        changelog = pl.DataFrame(
            {"issue_id": [], "to_status_id": [], "changed_at": []},
            schema={
                "issue_id": pl.Utf8,
                "to_status_id": pl.Utf8,
                "changed_at": pl.Datetime,
            },
        )
        board_columns = pl.DataFrame(
            {"status_id": [], "name": []},
            schema={"status_id": pl.Utf8, "name": pl.Utf8},
        )

        result = calculate_time_to_market(
            issues, issue_types, releases, fix_versions, changelog, board_columns
        )

        # Should only have Epic and Story
        assert result.height == 2
        assert "E1" in result["issue_id"]
        assert "S1" in result["issue_id"]
        assert "T1" not in result["issue_id"]

    def test_ttm_calculation_from_release_date(self):
        """Test TTM using fix version release date (Strategy 1)."""
        created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        release_date = datetime(2024, 1, 11, tzinfo=timezone.utc)  # 10 days later

        issues = pl.DataFrame(
            {
                "id": ["E1"],
                "key": ["K1"],
                "project_id": ["P1"],
                "type_id": ["TYPE-EPIC"],
                "jira_created_at": [created_at],
                "jira_resolved_at": [None],  # Not resolved yet, but released
            }
        )

        issue_types = pl.DataFrame(
            {"id": ["TYPE-EPIC"], "name": ["Epic"], "hierarchy_level": ["epic"]}
        )

        releases = pl.DataFrame({"id": ["V1"], "release_date": [release_date]})

        fix_versions = pl.DataFrame({"issue_id": ["E1"], "version_id": ["V1"]})

        # Empty others
        changelog = pl.DataFrame(
            {"issue_id": [], "to_status_id": [], "changed_at": []},
            schema={
                "issue_id": pl.Utf8,
                "to_status_id": pl.Utf8,
                "changed_at": pl.Datetime,
            },
        )
        board_columns = pl.DataFrame(
            {"status_id": [], "name": []},
            schema={"status_id": pl.Utf8, "name": pl.Utf8},
        )

        result = calculate_time_to_market(
            issues, issue_types, releases, fix_versions, changelog, board_columns
        )

        assert result.height == 1
        assert result["time_to_market_days"][0] == 10.0

    def test_ttm_calculation_from_done_status(self):
        """Test TTM using Done status transition (Strategy 2)."""
        created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        done_at = datetime(2024, 1, 6, tzinfo=timezone.utc)  # 5 days later

        issues = pl.DataFrame(
            {
                "id": ["E1"],
                "key": ["K1"],
                "project_id": ["P1"],
                "type_id": ["TYPE-EPIC"],
                "jira_created_at": [created_at],
                "jira_resolved_at": [None],
            }
        )

        issue_types = pl.DataFrame(
            {"id": ["TYPE-EPIC"], "name": ["Epic"], "hierarchy_level": ["epic"]}
        )

        changelog = pl.DataFrame(
            {
                "issue_id": ["E1"],
                "to_status_id": ["STATUS-DONE"],
                "changed_at": [done_at],
            }
        )

        board_columns = pl.DataFrame(
            {"status_id": ["STATUS-DONE"], "name": ["Done Column"]}
        )

        # Empty releases
        releases = pl.DataFrame(
            {"id": [], "release_date": []},
            schema={"id": pl.Utf8, "release_date": pl.Datetime},
        )
        fix_versions = pl.DataFrame(
            {"issue_id": [], "version_id": []},
            schema={"issue_id": pl.Utf8, "version_id": pl.Utf8},
        )

        result = calculate_time_to_market(
            issues, issue_types, releases, fix_versions, changelog, board_columns
        )

        assert result.height == 1
        assert result["time_to_market_days"][0] == 5.0

    def test_ttm_calculation_from_resolved_date(self):
        """Test TTM using resolved date (Strategy 3)."""
        created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        resolved_at = datetime(2024, 1, 3, tzinfo=timezone.utc)  # 2 days later

        issues = pl.DataFrame(
            {
                "id": ["E1"],
                "key": ["K1"],
                "project_id": ["P1"],
                "type_id": ["TYPE-EPIC"],
                "jira_created_at": [created_at],
                "jira_resolved_at": [resolved_at],
            }
        )

        issue_types = pl.DataFrame(
            {"id": ["TYPE-EPIC"], "name": ["Epic"], "hierarchy_level": ["epic"]}
        )

        # Empty others
        releases = pl.DataFrame(
            {"id": [], "release_date": []},
            schema={"id": pl.Utf8, "release_date": pl.Datetime},
        )
        fix_versions = pl.DataFrame(
            {"issue_id": [], "version_id": []},
            schema={"issue_id": pl.Utf8, "version_id": pl.Utf8},
        )
        changelog = pl.DataFrame(
            {"issue_id": [], "to_status_id": [], "changed_at": []},
            schema={
                "issue_id": pl.Utf8,
                "to_status_id": pl.Utf8,
                "changed_at": pl.Datetime,
            },
        )
        board_columns = pl.DataFrame(
            {"status_id": [], "name": []},
            schema={"status_id": pl.Utf8, "name": pl.Utf8},
        )

        result = calculate_time_to_market(
            issues, issue_types, releases, fix_versions, changelog, board_columns
        )

        assert result.height == 1
        assert result["time_to_market_days"][0] == 2.0
