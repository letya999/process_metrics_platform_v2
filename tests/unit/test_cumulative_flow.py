"""
Unit tests for Cumulative Flow Diagram (CFD) calculation logic.
"""

from datetime import datetime

import polars as pl

from pipelines.calculations.cumulative_flow import (
    _calculate_issue_status_on_dates,
    calculate_cfd_aggregates,
    calculate_cumulative_flow_diagram,
)


class TestCumulativeFlow:
    """Tests for calculate_cumulative_flow_diagram and related functions."""

    def test_calculate_issue_status_on_dates_basic(self):
        """Test determining issue status on dates."""
        # Issue 1: Created Jan 1, Status A. Changed to Status B on Jan 3.
        issues = pl.DataFrame(
            {
                "id": ["ISS-1"],
                "project_id": ["PROJ-1"],
                "status_id": ["STATUS-B"],  # Current status
                "jira_created_at": [datetime(2024, 1, 1)],
            }
        )

        date_range = pl.DataFrame(
            {
                "date": [
                    datetime(2024, 1, 1).date(),
                    datetime(2024, 1, 2).date(),
                    datetime(2024, 1, 3).date(),
                    datetime(2024, 1, 4).date(),
                ]
            }
        )

        status_changelog = pl.DataFrame(
            {
                "issue_id": ["ISS-1", "ISS-1"],
                "to_status_id": ["STATUS-A", "STATUS-B"],
                "changed_at": [
                    datetime(2024, 1, 1, 10, 0),
                    datetime(2024, 1, 3, 15, 0),
                ],
            }
        )

        result = _calculate_issue_status_on_dates(issues, status_changelog, date_range)

        # Expected:
        # Jan 1: STATUS-A
        # Jan 2: STATUS-A
        # Jan 3: STATUS-B (changed at 15:00, usually we take EOD or latest, logic takes "most recent status change before that date" - no wait)

        # Logic says: .filter(changed_at <= date).sort(changed_at desc).first()
        # Jan 1: changed_at (Jan 1 10:00) <= Jan 1 (00:00)? NO.
        # Wait, comparison of datetime vs date?
        # In the code: .filter(pl.col("changed_at").cast(pl.Date) <= pl.col("date"))

        # Jan 1: changed_at(Jan 1) <= date(Jan 1). Yes.
        # status_on_date for Jan 1 should be STATUS-A.
        # Jan 2: changed_at(Jan 1) <= date(Jan 2). status_on_date: STATUS-A.
        # Jan 3: changed_at(Jan 3 15:00) <= date(Jan 3). Yes. status_on_date: STATUS-B.

        jan_1 = result.filter(pl.col("date") == datetime(2024, 1, 1).date())[
            "status_id"
        ].to_list()[0]
        jan_2 = result.filter(pl.col("date") == datetime(2024, 1, 2).date())[
            "status_id"
        ].to_list()[0]
        jan_3 = result.filter(pl.col("date") == datetime(2024, 1, 3).date())[
            "status_id"
        ].to_list()[0]

        assert jan_1 == "STATUS-A"
        assert jan_2 == "STATUS-A"
        assert jan_3 == "STATUS-B"

    def test_calculate_cumulative_flow_diagram_integration(self):
        """Test full CFD calculation."""
        issues = pl.DataFrame(
            {
                "id": ["ISS-1"],
                "project_id": ["PROJ-1"],
                "status_id": ["S2"],
                "jira_created_at": [datetime(2024, 1, 1)],
            }
        )

        # S1 -> S2 on Jan 2
        changelog = pl.DataFrame(
            {
                "issue_id": ["ISS-1", "ISS-1"],
                "to_status_id": ["S1", "S2"],
                "changed_at": [datetime(2024, 1, 1), datetime(2026, 2, 2)],
            }
        )

        statuses = pl.DataFrame(
            {
                "id": ["S1", "S2"],
                "project_id": ["PROJ-1", "PROJ-1"],
                "name": ["Status 1", "Status 2"],
                "category": ["todo", "done"],
            }
        )

        boards = pl.DataFrame({})
        board_columns = pl.DataFrame(
            {"id": ["C1", "C2"], "status_id": ["S1", "S2"], "position": [1, 2]}
        )

        # Mock datetime.now() logic by expecting dates relative to today in the function,
        # but here we can just verify the output structure.

        result = calculate_cumulative_flow_diagram(
            issues, changelog, statuses, boards, board_columns, days_back=5
        )

        assert not result.is_empty()
        assert "issue_count" in result.columns
        assert "status_category" in result.columns

        # Verify counts roughly
        # We expect rows for S1 and S2
        s1_rows = result.filter(pl.col("status_name") == "Status 1")
        assert s1_rows.height > 0

    def test_cfd_join_error_regression(self):
        """
        Regression test for the 'datatypes of join keys don't match' error.
        We simulate a case where aggregation might produce a List type if not carefully cast.
        """
        issues = pl.DataFrame(
            {
                "id": ["ISS-1"],
                "project_id": ["PROJ-1"],
                "status_id": ["S1"],
                "jira_created_at": [datetime(2024, 1, 1)],
            }
        )

        # Using a changelog that might cause ambiguity if invalid
        changelog = pl.DataFrame(
            {
                "issue_id": ["ISS-1"],
                "to_status_id": ["S1"],
                "changed_at": [datetime(2024, 1, 1)],
            }
        )

        statuses = pl.DataFrame(
            {
                "id": ["S1"],
                "project_id": ["PROJ-1"],
                "name": ["Status 1"],
                "category": ["todo"],
            }
        )

        # This should run without PanicException or ComputeError
        result = calculate_cumulative_flow_diagram(
            issues, changelog, statuses, pl.DataFrame({}), pl.DataFrame({}), days_back=2
        )

        assert not result.is_empty()

    def test_calculate_issue_status_on_dates_empty_inputs(self):
        result = _calculate_issue_status_on_dates(
            pl.DataFrame(), pl.DataFrame(), pl.DataFrame()
        )
        assert result.is_empty()
        assert "issue_id" in result.columns

    def test_calculate_issue_status_on_dates_without_changelog(self):
        issues = pl.DataFrame(
            {
                "id": ["ISS-1"],
                "project_id": ["PROJ-1"],
                "status_id": ["S1"],
                "jira_created_at": [datetime(2024, 1, 1)],
            }
        )
        dates = pl.DataFrame({"date": [datetime(2024, 1, 1).date()]})
        result = _calculate_issue_status_on_dates(issues, pl.DataFrame(), dates)
        assert result.height == 1
        assert result["status_id"][0] == "S1"

    def test_calculate_cfd_handles_list_status_id(self, monkeypatch):
        issues = pl.DataFrame(
            {
                "id": ["ISS-1"],
                "project_id": ["PROJ-1"],
                "status_id": ["S1"],
                "jira_created_at": [datetime(2024, 1, 1)],
            }
        )
        statuses = pl.DataFrame(
            {
                "id": ["S1"],
                "project_id": ["PROJ-1"],
                "name": ["Status 1"],
                "category": ["todo"],
            }
        )

        monkeypatch.setattr(
            "pipelines.calculations.cumulative_flow._calculate_issue_status_on_dates",
            lambda *_args, **_kwargs: pl.DataFrame(
                {
                    "issue_id": ["ISS-1"],
                    "project_id": ["PROJ-1"],
                    "date": [datetime(2024, 1, 1).date()],
                    "status_id": [["S1"]],
                }
            ),
        )

        result = calculate_cumulative_flow_diagram(
            issues,
            pl.DataFrame(),
            statuses,
            pl.DataFrame(),
            pl.DataFrame(),
            days_back=1,
        )
        assert not result.is_empty()

    def test_calculate_cfd_aggregates_empty_and_trend(self):
        empty = calculate_cfd_aggregates(pl.DataFrame())
        assert empty.is_empty()

        cfd_df = pl.DataFrame(
            {
                "project_id": ["P1"] * 8,
                "status_name": ["In Progress"] * 8,
                "date": [datetime(2024, 1, i + 1).date() for i in range(8)],
                "issue_count": [1, 1, 1, 1, 1, 2, 2, 3],
            }
        )

        result = calculate_cfd_aggregates(cfd_df)
        assert result.height == 1
        assert result["trend"][0] in {"increasing", "decreasing", "stable"}
