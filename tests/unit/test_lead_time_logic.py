"""
Unit tests for Lead Time metrics calculation logic (Polars implementation)

These tests verify the business rules for determining:
- Commitment start/end points (In Progress → Done)
- Lead Time calculation
- Histogram bins creation
"""

from datetime import datetime

import polars as pl

from pipelines.calculations.commitment_resolver import (
    identify_commitment_points_heuristic as identify_commitment_points,
)
from pipelines.calculations.lead_time import (
    calculate_histogram_bins,
    calculate_lead_time_per_issue,
    calculate_lead_time_slice,
)


class TestCommitmentPoints:
    """Tests for identifying commitment points from board columns."""

    def test_identify_start_and_end_columns(self):
        """In Progress and Done columns are identified correctly."""
        board_columns = pl.DataFrame(
            {
                "id": ["COL-1", "COL-2", "COL-3"],
                "board_id": ["BOARD-1", "BOARD-1", "BOARD-1"],
                "name": ["To Do", "In Progress", "Done"],
                "position": [0, 1, 2],
                "status_id": ["STATUS-1", "STATUS-2", "STATUS-3"],
            }
        )

        points = identify_commitment_points(board_columns)

        assert len(points["start_status_ids"]) == 1
        assert points["start_status_ids"][0] == "STATUS-2"
        assert len(points["end_status_ids"]) == 1
        assert points["end_status_ids"][0] == "STATUS-3"
        # Middle should include "In Progress" status (position 1 <= x < 2)
        assert "STATUS-2" in points["middle_status_ids"]

    def test_empty_board_columns_returns_empty(self):
        """No board columns = no commitment points."""
        board_columns = pl.DataFrame(
            {"id": [], "board_id": [], "name": [], "position": [], "status_id": []},
            schema={
                "id": pl.Utf8,
                "board_id": pl.Utf8,
                "name": pl.Utf8,
                "position": pl.Int32,
                "status_id": pl.Utf8,
            },
        )

        points = identify_commitment_points(board_columns)

        assert not points["start_status_ids"]
        assert not points["end_status_ids"]

    def test_russian_column_names_are_recognized(self):
        """Russian column names (В работе, Готово) are recognized."""
        board_columns = pl.DataFrame(
            {
                "id": ["COL-1", "COL-2"],
                "board_id": ["BOARD-1", "BOARD-1"],
                "name": [
                    "В работе",  # 'В работе' means 'In Progress'
                    "Готово",  # 'Готово' means 'Done'
                ],
                "position": [1, 2],
                "status_id": ["STATUS-2", "STATUS-3"],
            }
        )

        points = identify_commitment_points(board_columns)

        assert len(points["start_status_ids"]) == 1
        assert len(points["end_status_ids"]) == 1


class TestLeadTimeCalculation:
    """Tests for calculating lead time per issue."""

    def test_calculate_lead_time_simple(self):
        """Test basic lead time calculation from start to end transition."""
        issues = pl.DataFrame(
            {
                "id": ["ISS-1"],
                "project_id": ["PROJ-1"],
                "key": ["PROJ-1"],
                "type_name": ["Story"],
                "jira_created_at": [datetime(2023, 12, 25, 10, 0)],
                "jira_resolved_at": [datetime(2024, 1, 10, 10, 0)],
            }
        )

        status_changelog = pl.DataFrame(
            {
                "issue_id": ["ISS-1", "ISS-1"],
                "from_status_id": [None, "STATUS-IN-PROGRESS"],
                "to_status_id": ["STATUS-IN-PROGRESS", "STATUS-DONE"],
                "changed_at": [
                    datetime(2024, 1, 1, 10, 0),  # Started
                    datetime(2024, 1, 6, 10, 0),  # Done (5 days later)
                ],
            }
        )

        result = calculate_lead_time_per_issue(
            issues,
            status_changelog,
            middle_status_ids=["STATUS-IN-PROGRESS"],  # Changed parameter name
            end_status_ids=["STATUS-DONE"],
        )

        assert len(result) == 1
        assert result["lead_time_days"][0] == 5.0

    def test_lead_time_only_counts_first_start_and_first_end(self):
        """Test that lead time uses the first start and first end after that start."""
        issues = pl.DataFrame(
            {
                "id": ["ISS-2"],
                "project_id": ["PROJ-1"],
                "key": ["PROJ-2"],
                "type_name": ["Bug"],
                "jira_created_at": [datetime(2023, 12, 25, 10, 0)],
                "jira_resolved_at": [datetime(2024, 1, 15, 10, 0)],
            }
        )

        status_changelog = pl.DataFrame(
            {
                "issue_id": ["ISS-2", "ISS-2", "ISS-2", "ISS-2"],
                "from_status_id": [
                    None,
                    "STATUS-IN-PROGRESS",
                    "STATUS-TODO",
                    "STATUS-IN-PROGRESS",
                ],
                "to_status_id": [
                    "STATUS-IN-PROGRESS",  # First start (Jan 1)
                    "STATUS-TODO",  # Moved back
                    "STATUS-IN-PROGRESS",  # Second start (ignored)
                    "STATUS-DONE",  # First end (Jan 10)
                ],
                "changed_at": [
                    datetime(2024, 1, 1, 10, 0),
                    datetime(2024, 1, 3, 10, 0),
                    datetime(2024, 1, 5, 10, 0),
                    datetime(2024, 1, 10, 10, 0),
                ],
            }
        )

        result = calculate_lead_time_per_issue(
            issues,
            status_changelog,
            middle_status_ids=["STATUS-IN-PROGRESS"],
            end_status_ids=["STATUS-DONE"],
        )

        # Lead time = Jan 1 to Jan 10 = 9 days (not Jan 5 to Jan 10)
        assert result["lead_time_days"][0] == 9.0

    def test_issue_without_end_event_uses_resolved_at(self):
        """Test fallback to jira_resolved_at when no explicit 'Done' transition exists."""
        issues = pl.DataFrame(
            {
                "id": ["ISS-3"],
                "project_id": ["PROJ-1"],
                "key": ["PROJ-3"],
                "type_name": ["Task"],
                "jira_created_at": [datetime(2023, 12, 25, 10, 0)],
                "jira_resolved_at": [datetime(2024, 1, 10, 10, 0)],  # Fallback
            }
        )

        status_changelog = pl.DataFrame(
            {
                "issue_id": ["ISS-3"],
                "from_status_id": [None],
                "to_status_id": ["STATUS-IN-PROGRESS"],
                "changed_at": [datetime(2024, 1, 1, 10, 0)],
            }
        )

        result = calculate_lead_time_per_issue(
            issues,
            status_changelog,
            middle_status_ids=["STATUS-IN-PROGRESS"],
            end_status_ids=["STATUS-DONE"],
        )

        # Should use resolved_at as end: Jan 1 to Jan 10 = 9 days
        assert len(result) == 1
        assert result["lead_time_days"][0] == 9.0

    def test_issue_without_commitment_zone_transition_is_excluded(self):
        """Test that issues skipping the commitment zone are excluded from calculation."""
        issues = pl.DataFrame(
            {
                "id": ["ISS-3B"],
                "project_id": ["PROJ-1"],
                "key": ["PROJ-3B"],
                "type_name": ["Task"],
                "jira_created_at": [datetime(2024, 1, 1, 10, 0)],
                "jira_resolved_at": [datetime(2024, 1, 10, 10, 0)],
            }
        )

        status_changelog = pl.DataFrame(
            {
                "issue_id": ["ISS-3B"],
                "from_status_id": [None],
                "to_status_id": ["STATUS-DONE"],
                "changed_at": [datetime(2024, 1, 10, 10, 0)],
            }
        )

        result = calculate_lead_time_per_issue(
            issues,
            status_changelog,
            middle_status_ids=["STATUS-IN-PROGRESS"],
            end_status_ids=["STATUS-DONE"],
        )

        # Should be empty because it never entered a middle status
        assert result.is_empty()

    def test_issue_entering_zone_at_middle_status_not_in_progress(self):
        """Test inclusion of issues entering at any middle status, not just 'In Progress'."""
        issues = pl.DataFrame(
            {
                "id": ["ISS-3C"],
                "project_id": ["PROJ-1"],
                "key": ["PROJ-3C"],
                "type_name": ["Task"],
                "jira_created_at": [datetime(2024, 1, 1, 10, 0)],
                "jira_resolved_at": [datetime(2024, 1, 12, 10, 0)],
            }
        )

        status_changelog = pl.DataFrame(
            {
                "issue_id": ["ISS-3C", "ISS-3C"],
                "from_status_id": [None, "STATUS-TESTING"],
                "to_status_id": ["STATUS-TESTING", "STATUS-DONE"],
                "changed_at": [
                    datetime(2024, 1, 3, 10, 0),  # first middle status (used as start)
                    datetime(2024, 1, 8, 10, 0),  # done
                ],
            }
        )

        result = calculate_lead_time_per_issue(
            issues,
            status_changelog,
            middle_status_ids=["STATUS-IN-PROGRESS", "STATUS-TESTING"],
            end_status_ids=["STATUS-DONE"],
        )

        assert len(result) == 1
        assert result["commitment_start_at"][0] == datetime(2024, 1, 3, 10, 0)
        assert result["lead_time_days"][0] == 5.0

    def test_lead_time_ceil_fractional_hours(self):
        """Test that fractional days are ceiled to the next whole day."""
        issues = pl.DataFrame(
            {
                "id": ["ISS-F1"],
                "project_id": ["P1"],
                "key": ["K1"],
                "type_name": ["Task"],
                "jira_created_at": [datetime(2024, 1, 1, 0, 0)],
                "jira_resolved_at": [datetime(2024, 1, 1, 13, 0)],
            }
        )
        status_changelog = pl.DataFrame(
            {
                "issue_id": ["ISS-F1", "ISS-F1"],
                "from_status_id": [None, "STATUS-IN-PROGRESS"],
                "to_status_id": ["STATUS-IN-PROGRESS", "STATUS-DONE"],
                "changed_at": [
                    datetime(2024, 1, 1, 8, 0),
                    datetime(2024, 1, 1, 13, 0),
                ],
            }
        )
        result = calculate_lead_time_per_issue(
            issues, status_changelog, ["STATUS-IN-PROGRESS"], ["STATUS-DONE"]
        )
        assert result["lead_time_days"][0] == 1.0

    def test_lead_time_ceil_25_hours(self):
        """Test that 25 hours is correctly ceiled to 2.0 days."""
        issues = pl.DataFrame(
            {
                "id": ["ISS-F2"],
                "project_id": ["P1"],
                "key": ["K2"],
                "type_name": ["Task"],
                "jira_created_at": [datetime(2024, 1, 1, 0, 0)],
                "jira_resolved_at": [datetime(2024, 1, 2, 11, 0)],
            }
        )
        status_changelog = pl.DataFrame(
            {
                "issue_id": ["ISS-F2", "ISS-F2"],
                "from_status_id": [None, "STATUS-IN-PROGRESS"],
                "to_status_id": ["STATUS-IN-PROGRESS", "STATUS-DONE"],
                "changed_at": [
                    datetime(2024, 1, 1, 10, 0),
                    datetime(2024, 1, 2, 11, 0),  # 25 hours
                ],
            }
        )
        result = calculate_lead_time_per_issue(
            issues, status_changelog, ["STATUS-IN-PROGRESS"], ["STATUS-DONE"]
        )
        assert result["lead_time_days"][0] == 2.0

    def test_lead_time_ceil_exactly_24_hours(self):
        """Test that exactly 24 hours is calculated as 1.0 day."""
        issues = pl.DataFrame(
            {
                "id": ["ISS-F3"],
                "project_id": ["P1"],
                "key": ["K3"],
                "type_name": ["Task"],
                "jira_created_at": [datetime(2024, 1, 1, 0, 0)],
                "jira_resolved_at": [datetime(2024, 1, 2, 10, 0)],
            }
        )
        status_changelog = pl.DataFrame(
            {
                "issue_id": ["ISS-F3", "ISS-F3"],
                "from_status_id": [None, "STATUS-IN-PROGRESS"],
                "to_status_id": ["STATUS-IN-PROGRESS", "STATUS-DONE"],
                "changed_at": [
                    datetime(2024, 1, 1, 10, 0),
                    datetime(2024, 1, 2, 10, 0),  # exactly 24h
                ],
            }
        )
        result = calculate_lead_time_per_issue(
            issues, status_changelog, ["STATUS-IN-PROGRESS"], ["STATUS-DONE"]
        )
        assert result["lead_time_days"][0] == 1.0

    def test_issue_with_no_end_status_and_no_resolved_at_is_excluded(self):
        """Test exclusion of issues with no end status and no resolved date."""
        issues = pl.DataFrame(
            {
                "id": ["ISS-NOEND"],
                "project_id": ["P1"],
                "key": ["K1"],
                "type_name": ["Task"],
                "jira_created_at": [datetime(2024, 1, 1, 0, 0)],
                "jira_resolved_at": [None],
            }
        )
        status_changelog = pl.DataFrame(
            {
                "issue_id": ["ISS-NOEND"],
                "from_status_id": [None],
                "to_status_id": ["STATUS-IN-PROGRESS"],
                "changed_at": [datetime(2024, 1, 1, 10, 0)],
            }
        )
        result = calculate_lead_time_per_issue(
            issues, status_changelog, ["STATUS-IN-PROGRESS"], ["STATUS-DONE"]
        )
        assert result.is_empty()

    def test_multiple_issues_mix_included_and_excluded(self):
        """Test a mix of valid and invalid issues in a single calculation batch."""
        issues = pl.DataFrame(
            {
                "id": ["A", "B", "C"],
                "project_id": ["P1", "P1", "P1"],
                "key": ["A", "B", "C"],
                "type_name": ["Task", "Task", "Task"],
                "jira_created_at": [datetime(2024, 1, 1)] * 3,
                "jira_resolved_at": [datetime(2024, 1, 10)] * 3,
            }
        )
        status_changelog = pl.DataFrame(
            {
                "issue_id": ["A", "A", "B", "C", "C"],
                "from_status_id": [
                    None,
                    "STATUS-IN-PROGRESS",
                    None,
                    None,
                    "STATUS-TESTING",
                ],
                "to_status_id": [
                    "STATUS-IN-PROGRESS",
                    "STATUS-DONE",
                    "STATUS-DONE",  # B: skipped commitment
                    "STATUS-TESTING",
                    "STATUS-DONE",
                ],
                "changed_at": [
                    datetime(2024, 1, 2),
                    datetime(2024, 1, 5),
                    datetime(2024, 1, 5),
                    datetime(2024, 1, 2),
                    datetime(2024, 1, 7),
                ],
            }
        )
        result = calculate_lead_time_per_issue(
            issues,
            status_changelog,
            ["STATUS-IN-PROGRESS", "STATUS-TESTING"],
            ["STATUS-DONE"],
        )
        assert len(result) == 2
        assert sorted(result["issue_id"].to_list()) == ["A", "C"]

    def test_pre_reset_commitment_start_after_last_done_exit(self):
        """Test that commitment start is correctly reset after an issue is reopened from Done."""
        issues = pl.DataFrame(
            {
                "id": ["ISS-5"],
                "project_id": ["PROJ-1"],
                "key": ["PROJ-5"],
                "type_name": ["Bug"],
                "jira_created_at": [datetime(2023, 12, 25, 10, 0)],
                "jira_resolved_at": [datetime(2024, 1, 20, 10, 0)],
            }
        )

        status_changelog = pl.DataFrame(
            {
                "issue_id": ["ISS-5", "ISS-5", "ISS-5", "ISS-5"],
                "from_status_id": [
                    None,
                    "STATUS-IN-PROGRESS",
                    "STATUS-DONE",
                    "STATUS-IN-PROGRESS",
                ],
                "to_status_id": [
                    "STATUS-IN-PROGRESS",  # First start: Jan 1 (IGNORED, before last Done exit)
                    "STATUS-DONE",  # First done: Jan 5
                    "STATUS-IN-PROGRESS",  # Left done: Jan 8 (THIS is the start of current lifecycle)
                    "STATUS-DONE",  # Final done: Jan 15
                ],
                "changed_at": [
                    datetime(2024, 1, 1, 10, 0),
                    datetime(2024, 1, 5, 10, 0),  # First Done
                    datetime(2024, 1, 8, 10, 0),  # Left Done
                    datetime(2024, 1, 15, 10, 0),  # Final Done
                ],
            }
        )

        result = calculate_lead_time_per_issue(
            issues,
            status_changelog,
            middle_status_ids=["STATUS-IN-PROGRESS"],
            end_status_ids=["STATUS-DONE"],
        )

        # Start = Jan 8, End = Jan 15 -> 7.0 days
        assert len(result) == 1
        assert result["commitment_start_at"][0] == datetime(2024, 1, 8, 10, 0)
        assert result["lead_time_days"][0] == 7.0


class TestHistogramBins:
    """Tests for histogram bins calculation."""

    def test_calculate_bins(self):
        """Test that lead time values are correctly binned using ceiling logic."""
        lead_time_df = pl.DataFrame(
            {
                "issue_id": ["ISS-1", "ISS-2", "ISS-3", "ISS-4"],
                "project_id": ["PROJ-1", "PROJ-1", "PROJ-1", "PROJ-1"],
                "lead_time_days": [1.5, 2.9, 3.0, 5.1],
            }
        )

        result = calculate_histogram_bins(lead_time_df)

        # 1.5 → bin 2, 2.9 → bin 3, 3.0 → bin 3, 5.1 → bin 6
        assert len(result) == 3  # 3 unique bins (2, 3, 6)

        bin_2_count = result.filter(pl.col("bin_number") == 2)["tickets_count"][0]
        assert bin_2_count == 1

        bin_3_count = result.filter(pl.col("bin_number") == 3)["tickets_count"][0]
        assert bin_3_count == 2

    def test_empty_lead_time_returns_empty_bins(self):
        """Test that empty input produces empty histogram bins."""
        lead_time_df = pl.DataFrame(
            {"issue_id": [], "project_id": [], "lead_time_days": []},
            schema={
                "issue_id": pl.Utf8,
                "project_id": pl.Utf8,
                "lead_time_days": pl.Float64,
            },
        )

        result = calculate_histogram_bins(lead_time_df)

        assert result.is_empty()


class TestLeadTimeSlice:
    """Tests for lead time aggregation by issue type."""

    def test_calculate_slice_by_issue_type(self):
        """Test aggregation of lead time statistics by issue type."""
        lead_time_df = pl.DataFrame(
            {
                "issue_id": ["ISS-1", "ISS-2", "ISS-3"],
                "project_id": ["PROJ-1", "PROJ-1", "PROJ-1"],
                "issue_type": ["Story", "Story", "Bug"],
                "lead_time_days": [5.0, 7.0, 10.0],
            }
        )

        result = calculate_lead_time_slice(lead_time_df)

        assert len(result) == 2  # 2 issue types

        story_row = result.filter(pl.col("issue_type") == "Story")
        assert story_row["total_issues"][0] == 2
        assert story_row["avg_lead_time_days"][0] == 6.0  # (5+7)/2

        bug_row = result.filter(pl.col("issue_type") == "Bug")
        assert bug_row["total_issues"][0] == 1
        assert bug_row["avg_lead_time_days"][0] == 10.0

    def test_empty_lead_time_returns_empty_slice(self):
        """Test that empty input produces empty sliced results."""
        lead_time_df = pl.DataFrame(
            {"issue_id": [], "project_id": [], "issue_type": [], "lead_time_days": []},
            schema={
                "issue_id": pl.Utf8,
                "project_id": pl.Utf8,
                "issue_type": pl.Utf8,
                "lead_time_days": pl.Float64,
            },
        )

        result = calculate_lead_time_slice(lead_time_df)

        assert result.is_empty()


def test_calculate_histogram_bins_slice():
    """Test histogram bins calculation when grouped by slice (issue type)."""
    from pipelines.calculations.lead_time import calculate_histogram_bins_slice

    # Empty
    res_empty = calculate_histogram_bins_slice(
        pl.DataFrame(
            schema={
                "project_id": pl.Utf8,
                "issue_type": pl.Utf8,
                "lead_time_days": pl.Float64,
            }
        )
    )
    assert res_empty.is_empty()

    # Happy path
    df = pl.DataFrame(
        {
            "project_id": ["P1", "P1", "P1"],
            "issue_type": ["Story", "Story", "Bug"],
            "lead_time_days": [1.2, 1.8, 0.5],
        }
    )
    res = calculate_histogram_bins_slice(df)
    assert res.height == 2  # Story bin 2, Bug bin 1
    # Story bin 2 should have count 2
    assert (
        res.filter((pl.col("issue_type") == "Story") & (pl.col("bin_number") == 2))[
            "tickets_count"
        ][0]
        == 2
    )
    # Bug bin 1 should have count 1
    assert (
        res.filter((pl.col("issue_type") == "Bug") & (pl.col("bin_number") == 1))[
            "tickets_count"
        ][0]
        == 1
    )
