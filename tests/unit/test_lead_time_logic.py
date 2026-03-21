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
                "name": ["В работе", "Готово"],
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
        """Basic lead time calculation: start to end."""
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
        """Lead time uses FIRST start and FIRST end (after start)."""
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
        """Issue without Done event falls back to jira_resolved_at."""
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

    def test_issue_without_start_event_uses_created_at(self):
        """Issue without In Progress event falls back to jira_created_at."""
        issues = pl.DataFrame(
            {
                "id": ["ISS-3B"],
                "project_id": ["PROJ-1"],
                "key": ["PROJ-3B"],
                "type_name": ["Task"],
                "jira_created_at": [datetime(2024, 1, 1, 10, 0)],  # Fallback
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

        # Should use created_at as start: Jan 1 to Jan 10 = 9 days
        assert len(result) == 1
        assert result["lead_time_days"][0] == 9.0

    def test_start_can_come_from_middle_status_when_in_progress_missing(self):
        """If issue never entered In Progress, start can be another middle status."""
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
                "from_status_id": [None, "STATUS-CODE-REVIEW"],
                "to_status_id": ["STATUS-CODE-REVIEW", "STATUS-DONE"],
                "changed_at": [
                    datetime(2024, 1, 3, 10, 0),  # first middle status (used as start)
                    datetime(2024, 1, 8, 10, 0),  # done
                ],
            }
        )

        result = calculate_lead_time_per_issue(
            issues,
            status_changelog,
            middle_status_ids=["STATUS-IN-PROGRESS", "STATUS-CODE-REVIEW"],
            end_status_ids=["STATUS-DONE"],
        )

        assert len(result) == 1
        assert result["commitment_start_at"][0] == datetime(2024, 1, 3, 10, 0)
        assert result["lead_time_days"][0] == 5.0

    def test_start_ignores_statuses_before_middle_range(self):
        """Start is taken from first middle status, not earlier outside-range statuses."""
        issues = pl.DataFrame(
            {
                "id": ["ISS-3D"],
                "project_id": ["PROJ-1"],
                "key": ["PROJ-3D"],
                "type_name": ["Task"],
                "jira_created_at": [datetime(2024, 1, 1, 10, 0)],
                "jira_resolved_at": [datetime(2024, 1, 15, 10, 0)],
            }
        )

        status_changelog = pl.DataFrame(
            {
                "issue_id": ["ISS-3D", "ISS-3D", "ISS-3D"],
                "from_status_id": [None, "STATUS-TODO", "STATUS-CODE-REVIEW"],
                "to_status_id": ["STATUS-TODO", "STATUS-CODE-REVIEW", "STATUS-DONE"],
                "changed_at": [
                    datetime(2024, 1, 2, 10, 0),  # outside middle range
                    datetime(2024, 1, 4, 10, 0),  # first middle status (used as start)
                    datetime(2024, 1, 9, 10, 0),  # done
                ],
            }
        )

        result = calculate_lead_time_per_issue(
            issues,
            status_changelog,
            middle_status_ids=["STATUS-IN-PROGRESS", "STATUS-CODE-REVIEW"],
            end_status_ids=["STATUS-DONE"],
        )

        assert len(result) == 1
        assert result["commitment_start_at"][0] == datetime(2024, 1, 4, 10, 0)
        assert result["lead_time_days"][0] == 5.0

    def test_empty_status_ids_returns_empty(self):
        """No middle/end status IDs = no lead time."""
        issues = pl.DataFrame(
            {
                "id": ["ISS-4"],
                "project_id": ["PROJ-1"],
                "key": ["PROJ-4"],
                "type_name": ["Story"],
                "jira_created_at": [datetime(2024, 1, 1, 10, 0)],
                "jira_resolved_at": [datetime(2024, 1, 10, 10, 0)],
            }
        )

        status_changelog = pl.DataFrame(
            {
                "issue_id": ["ISS-4"],
                "from_status_id": [None],
                "to_status_id": ["STATUS-DONE"],
                "changed_at": [datetime(2024, 1, 10, 10, 0)],
            }
        )

        result = calculate_lead_time_per_issue(
            issues,
            status_changelog,
            middle_status_ids=[],  # Empty
            end_status_ids=["STATUS-DONE"],
        )

        assert result.is_empty()

    def test_issue_returning_to_done_uses_last_left_end_logic(self):
        """Issue that left Done and returned uses correct end date."""
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
                    "STATUS-IN-PROGRESS",  # Start: Jan 1
                    "STATUS-DONE",  # First done: Jan 5 (should be ignored)
                    "STATUS-IN-PROGRESS",  # Left done: Jan 8
                    "STATUS-DONE",  # Final done: Jan 15 (should be used)
                ],
                "changed_at": [
                    datetime(2024, 1, 1, 10, 0),
                    datetime(2024, 1, 5, 10, 0),  # First Done (ignored)
                    datetime(2024, 1, 8, 10, 0),  # Left Done
                    datetime(2024, 1, 15, 10, 0),  # Final Done (used)
                ],
            }
        )

        result = calculate_lead_time_per_issue(
            issues,
            status_changelog,
            middle_status_ids=["STATUS-IN-PROGRESS"],
            end_status_ids=["STATUS-DONE"],
        )

        # Lead time = Jan 1 (first start) to Jan 15 (final done after leaving) = 14 days
        assert len(result) == 1
        assert result["lead_time_days"][0] == 14.0


class TestHistogramBins:
    """Tests for histogram bins calculation."""

    def test_calculate_bins(self):
        """Bins are created correctly (ceiling of days)."""
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
        """Empty lead time = empty bins."""
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
        """Lead time aggregated by issue type."""
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
        """Empty lead time = empty slice."""
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
    """Test histogram bins by slice (issue type)."""
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
