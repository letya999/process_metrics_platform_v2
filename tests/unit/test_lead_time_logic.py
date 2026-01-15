"""
Unit tests for Lead Time metrics calculation logic (Polars implementation)

These tests verify the business rules for determining:
- Commitment start/end points (In Progress → Done)
- Lead Time calculation
- Histogram bins creation
"""

from datetime import datetime

import polars as pl

from pipelines.calculations.lead_time import (
    calculate_histogram_bins,
    calculate_lead_time_per_issue,
    calculate_lead_time_slice,
    identify_commitment_points,
)


class TestCommitmentPoints:
    """Tests for identifying commitment points from board columns."""

    def test_identify_start_and_end_columns(self):
        """In Progress and Done columns are identified correctly."""
        boards = pl.DataFrame({"id": ["BOARD-1"], "project_id": ["PROJ-1"]})

        board_columns = pl.DataFrame(
            {
                "id": ["COL-1", "COL-2", "COL-3"],
                "board_id": ["BOARD-1", "BOARD-1", "BOARD-1"],
                "name": ["To Do", "In Progress", "Done"],
                "status_id": ["STATUS-1", "STATUS-2", "STATUS-3"],
            }
        )

        start_cols, end_cols = identify_commitment_points(boards, board_columns)

        assert len(start_cols) == 1
        assert start_cols["status_id"][0] == "STATUS-2"
        assert len(end_cols) == 1
        assert end_cols["status_id"][0] == "STATUS-3"

    def test_empty_board_columns_returns_empty(self):
        """No board columns = no commitment points."""
        boards = pl.DataFrame({"id": [], "project_id": []})
        board_columns = pl.DataFrame(
            {"id": [], "board_id": [], "name": [], "status_id": []},
            schema={
                "id": pl.Utf8,
                "board_id": pl.Utf8,
                "name": pl.Utf8,
                "status_id": pl.Utf8,
            },
        )

        start_cols, end_cols = identify_commitment_points(boards, board_columns)

        assert start_cols.is_empty()
        assert end_cols.is_empty()

    def test_russian_column_names_are_recognized(self):
        """Russian column names (В работе, Готово) are recognized."""
        boards = pl.DataFrame({"id": ["BOARD-1"], "project_id": ["PROJ-1"]})

        board_columns = pl.DataFrame(
            {
                "id": ["COL-1", "COL-2"],
                "board_id": ["BOARD-1", "BOARD-1"],
                "name": ["В работе", "Готово"],
                "status_id": ["STATUS-2", "STATUS-3"],
            }
        )

        start_cols, end_cols = identify_commitment_points(boards, board_columns)

        assert len(start_cols) == 1
        assert len(end_cols) == 1


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
            }
        )

        status_changelog = pl.DataFrame(
            {
                "issue_id": ["ISS-1", "ISS-1"],
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
            start_status_ids=["STATUS-IN-PROGRESS"],
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
            }
        )

        status_changelog = pl.DataFrame(
            {
                "issue_id": ["ISS-2", "ISS-2", "ISS-2", "ISS-2"],
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
            start_status_ids=["STATUS-IN-PROGRESS"],
            end_status_ids=["STATUS-DONE"],
        )

        # Lead time = Jan 1 to Jan 10 = 9 days (not Jan 5 to Jan 10)
        assert result["lead_time_days"][0] == 9.0

    def test_issue_without_end_event_is_excluded(self):
        """Issue without Done event = no lead time."""
        issues = pl.DataFrame(
            {
                "id": ["ISS-3"],
                "project_id": ["PROJ-1"],
                "key": ["PROJ-3"],
                "type_name": ["Task"],
            }
        )

        status_changelog = pl.DataFrame(
            {
                "issue_id": ["ISS-3"],
                "to_status_id": ["STATUS-IN-PROGRESS"],
                "changed_at": [datetime(2024, 1, 1, 10, 0)],
            }
        )

        result = calculate_lead_time_per_issue(
            issues,
            status_changelog,
            start_status_ids=["STATUS-IN-PROGRESS"],
            end_status_ids=["STATUS-DONE"],
        )

        assert result.is_empty()

    def test_empty_status_ids_returns_empty(self):
        """No start/end status IDs = no lead time."""
        issues = pl.DataFrame(
            {
                "id": ["ISS-4"],
                "project_id": ["PROJ-1"],
                "key": ["PROJ-4"],
                "type_name": ["Story"],
            }
        )

        status_changelog = pl.DataFrame(
            {
                "issue_id": ["ISS-4"],
                "to_status_id": ["STATUS-DONE"],
                "changed_at": [datetime(2024, 1, 10, 10, 0)],
            }
        )

        result = calculate_lead_time_per_issue(
            issues,
            status_changelog,
            start_status_ids=[],  # Empty
            end_status_ids=["STATUS-DONE"],
        )

        assert result.is_empty()


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
