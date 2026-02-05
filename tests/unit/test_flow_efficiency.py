"""
Unit tests for Flow Efficiency calculation logic.
"""

from datetime import datetime

import polars as pl

from pipelines.calculations.flow_efficiency import (
    _calculate_intervals,
    calculate_flow_efficiency,
)


class TestFlowEfficiency:
    """Tests for calculate_flow_efficiency."""

    def test_calculate_flow_efficiency_basic(self):
        """Test basic flow efficiency calculation."""
        # Issue history:
        # Day 1: To Do -> In Progress (Active)
        # Day 2: In Progress -> Blocked (Wait)
        # Day 3: Blocked -> Done (Active end)

        # Total duration = 2 days (Day 1 to 3).
        # Active: 1 day (To Do -> In Progress -> Blocked)
        # Wait: 1 day (Blocked -> Done)
        # Efficiency = 1 / (1+1) = 50%

        # Setup DFs
        issues = pl.DataFrame(
            {
                "id": ["ISS-1"],
                "project_id": ["PROJ-1"],
                "key": ["KEY-1"],
                "type_name": ["Task"],
            }
        )

        start_time = datetime(2024, 1, 1, 10, 0)
        mid_time = datetime(2024, 1, 2, 10, 0)
        end_time = datetime(2024, 1, 3, 10, 0)

        changelog = pl.DataFrame(
            {
                "issue_id": ["ISS-1", "ISS-1", "ISS-1"],
                "to_status_id": ["STATUS-Active", "STATUS-Wait", "STATUS-Done"],
                "changed_at": [start_time, mid_time, end_time],
            }
        )

        boards = pl.DataFrame({"id": ["BOARD-1"], "project_id": ["PROJ-1"]})
        board_columns = pl.DataFrame(
            {
                "status_id": ["STATUS-Active", "STATUS-Wait", "STATUS-Done"],
                "name": ["In Progress", "Blocked", "Done"],
                "position": [1, 2, 3],  # Done is usually end
            }
        )

        # We need to ensure "In Progress" and "Blocked" are considered "middle" (between start and end).
        # Using lead_time logic (which flow_efficiency imports), columns between first and last are middle.

        result = calculate_flow_efficiency(
            issues, changelog, boards, board_columns, wait_status_ids=["STATUS-Wait"]
        )

        assert not result.is_empty()
        assert result["flow_efficiency_pct"][0] == 50.0
        assert result["active_days"][0] == 1.0
        assert result["wait_days"][0] == 1.0

    def test_calculate_intervals_logic(self):
        """Test helper _calculate_intervals."""
        dt1 = datetime(2024, 1, 1)
        dt2 = datetime(2024, 1, 2)

        data = pl.DataFrame({"changed_at": [dt1, dt2], "to_status_id": ["A", "B"]})

        output = _calculate_intervals(data)

        # Should have 1 interval: A -> B, duration 1 day
        # Last row filtered out because no next_change_at
        assert output.height == 1
        assert output["duration_days"][0] == 1.0
        assert output["status_id"][0] == "A"

    def test_flow_efficiency_empty(self):
        """Test empty input handling."""
        result = calculate_flow_efficiency(
            pl.DataFrame({}), pl.DataFrame({}), pl.DataFrame({}), pl.DataFrame({})
        )
        assert result.is_empty()
        assert "flow_efficiency_pct" in result.columns
