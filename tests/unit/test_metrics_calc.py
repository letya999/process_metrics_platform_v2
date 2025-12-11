"""Unit tests for metrics calculation utilities.

Tests the calculation functions in pipelines/utils/metrics.py
"""

from datetime import datetime, timezone

import pytest

from pipelines.utils.metrics import (
    calculate_cycle_time,
    calculate_lead_time,
    calculate_lead_time_percentiles,
    calculate_sprint_velocity,
    calculate_throughput,
    detect_work_start_from_changelog,
)


class TestCalculateLeadTime:
    """Tests for calculate_lead_time function."""

    def test_calculate_lead_time_basic(self):
        """Test basic lead time calculation."""
        created = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        resolved = datetime(2024, 1, 6, 0, 0, 0, tzinfo=timezone.utc)

        result = calculate_lead_time(created, resolved)

        assert result["lead_time_days"] == 5.0
        assert result["lead_time_hours"] == 120.0

    def test_calculate_lead_time_with_hours(self):
        """Test lead time calculation with fractional days."""
        created = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        resolved = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        result = calculate_lead_time(created, resolved)

        assert result["lead_time_days"] == 0.5
        assert result["lead_time_hours"] == 12.0

    def test_calculate_lead_time_none_created(self):
        """Test lead time with None created_at."""
        resolved = datetime(2024, 1, 6, 0, 0, 0, tzinfo=timezone.utc)

        result = calculate_lead_time(None, resolved)

        assert result["lead_time_days"] is None
        assert result["lead_time_hours"] is None

    def test_calculate_lead_time_none_resolved(self):
        """Test lead time with None resolved_at."""
        created = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        result = calculate_lead_time(created, None)

        assert result["lead_time_days"] is None
        assert result["lead_time_hours"] is None

    def test_calculate_lead_time_same_day(self):
        """Test lead time when resolved same day."""
        created = datetime(2024, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
        resolved = datetime(2024, 1, 1, 17, 0, 0, tzinfo=timezone.utc)

        result = calculate_lead_time(created, resolved)

        assert result["lead_time_hours"] == 8.0
        assert result["lead_time_days"] == pytest.approx(8.0 / 24.0, rel=0.01)


class TestCalculateCycleTime:
    """Tests for calculate_cycle_time function."""

    def test_calculate_cycle_time_basic(self):
        """Test basic cycle time calculation."""
        started = datetime(2024, 1, 3, 0, 0, 0, tzinfo=timezone.utc)
        resolved = datetime(2024, 1, 6, 0, 0, 0, tzinfo=timezone.utc)

        result = calculate_cycle_time(started, resolved)

        assert result["cycle_time_days"] == 3.0
        assert result["cycle_time_hours"] == 72.0

    def test_calculate_cycle_time_none_started(self):
        """Test cycle time with None started_at."""
        resolved = datetime(2024, 1, 6, 0, 0, 0, tzinfo=timezone.utc)

        result = calculate_cycle_time(None, resolved)

        assert result["cycle_time_days"] is None
        assert result["cycle_time_hours"] is None


class TestCalculateSprintVelocity:
    """Tests for calculate_sprint_velocity function."""

    def test_calculate_velocity_basic(self, sample_issues_for_velocity):
        """Test basic velocity calculation."""
        result = calculate_sprint_velocity(sample_issues_for_velocity)

        assert result["total_issues"] == 5
        assert result["completed_issues"] == 3
        assert result["completion_rate_pct"] == 60.0

    def test_calculate_velocity_story_points(self, sample_issues_for_velocity):
        """Test velocity calculation with story points."""
        result = calculate_sprint_velocity(sample_issues_for_velocity)

        assert result["total_story_points"] == 18.0  # 5 + 3 + 8 + 2
        assert result["completed_story_points"] == 10.0  # 5 + 3 + 2

    def test_calculate_velocity_empty_sprint(self):
        """Test velocity calculation with empty sprint."""
        result = calculate_sprint_velocity([])

        assert result["total_issues"] == 0
        assert result["completed_issues"] == 0
        assert result["completion_rate_pct"] == 0.0

    def test_calculate_velocity_custom_done_statuses(self):
        """Test velocity with custom done statuses."""
        issues = [
            {"status_name": "Completed", "story_points": 5},
            {"status_name": "Shipped", "story_points": 3},
            {"status_name": "Open", "story_points": 8},
        ]
        result = calculate_sprint_velocity(
            issues,
            done_statuses=["Completed", "Shipped"],
        )

        assert result["completed_issues"] == 2
        assert result["completed_story_points"] == 8.0

    def test_calculate_velocity_all_done(self):
        """Test velocity when all issues are done."""
        issues = [
            {"status_name": "Done", "story_points": 5},
            {"status_name": "Done", "story_points": 3},
        ]
        result = calculate_sprint_velocity(issues)

        assert result["completion_rate_pct"] == 100.0


class TestCalculateThroughput:
    """Tests for calculate_throughput function."""

    def test_calculate_throughput_basic(self):
        """Test basic throughput calculation."""
        issues = [
            {"resolved_at": datetime(2024, 1, 1, tzinfo=timezone.utc)},
            {"resolved_at": datetime(2024, 1, 1, tzinfo=timezone.utc)},
            {"resolved_at": datetime(2024, 1, 2, tzinfo=timezone.utc)},
            {"resolved_at": datetime(2024, 1, 3, tzinfo=timezone.utc)},
        ]
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 3, tzinfo=timezone.utc)

        result = calculate_throughput(issues, start, end)

        assert result["total_issues_completed"] == 4
        assert result["days_in_range"] == 3
        assert result["avg_daily_throughput"] == pytest.approx(4 / 3, rel=0.01)

    def test_calculate_throughput_by_date(self):
        """Test throughput grouped by date."""
        issues = [
            {"resolved_at": datetime(2024, 1, 1, tzinfo=timezone.utc)},
            {"resolved_at": datetime(2024, 1, 1, tzinfo=timezone.utc)},
            {"resolved_at": datetime(2024, 1, 2, tzinfo=timezone.utc)},
        ]
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 2, tzinfo=timezone.utc)

        result = calculate_throughput(issues, start, end)

        assert result["by_date"]["2024-01-01"] == 2
        assert result["by_date"]["2024-01-02"] == 1

    def test_calculate_throughput_empty(self):
        """Test throughput with no issues."""
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 7, tzinfo=timezone.utc)

        result = calculate_throughput([], start, end)

        assert result["total_issues_completed"] == 0
        assert result["avg_daily_throughput"] == 0.0

    def test_calculate_throughput_filters_out_of_range(self):
        """Test that issues outside date range are filtered."""
        issues = [
            {"resolved_at": datetime(2024, 1, 1, tzinfo=timezone.utc)},
            {"resolved_at": datetime(2024, 1, 15, tzinfo=timezone.utc)},  # Out of range
        ]
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 7, tzinfo=timezone.utc)

        result = calculate_throughput(issues, start, end)

        assert result["total_issues_completed"] == 1


class TestCalculateLeadTimePercentiles:
    """Tests for calculate_lead_time_percentiles function."""

    def test_calculate_percentiles_basic(self):
        """Test basic percentile calculation."""
        lead_times = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]

        result = calculate_lead_time_percentiles(lead_times)

        assert result["p50"] is not None
        assert result["p75"] is not None
        assert result["p85"] is not None
        assert result["p95"] is not None
        assert result["avg"] == 5.5

    def test_calculate_percentiles_sorted(self):
        """Test that percentiles are calculated correctly regardless of order."""
        lead_times_unsorted = [10.0, 1.0, 5.0, 3.0, 8.0]
        lead_times_sorted = sorted(lead_times_unsorted)

        result1 = calculate_lead_time_percentiles(lead_times_unsorted)
        result2 = calculate_lead_time_percentiles(lead_times_sorted)

        assert result1["p50"] == result2["p50"]
        assert result1["avg"] == result2["avg"]

    def test_calculate_percentiles_empty(self):
        """Test percentiles with empty list."""
        result = calculate_lead_time_percentiles([])

        assert result["p50"] is None
        assert result["p75"] is None
        assert result["avg"] is None

    def test_calculate_percentiles_single_value(self):
        """Test percentiles with single value."""
        result = calculate_lead_time_percentiles([5.0])

        assert result["p50"] == 5.0
        assert result["avg"] == 5.0


class TestDetectWorkStartFromChangelog:
    """Tests for detect_work_start_from_changelog function."""

    def test_detect_work_start_basic(self):
        """Test detecting when work started from changelog."""
        dt1 = datetime(2024, 1, 2, 10, 0, 0, tzinfo=timezone.utc)
        dt2 = datetime(2024, 1, 3, 10, 0, 0, tzinfo=timezone.utc)

        changelog_items = [
            {"to_value": "Open", "changed_at": dt1},
            {"to_value": "In Progress", "changed_at": dt2},
        ]

        result = detect_work_start_from_changelog(changelog_items)

        assert result == dt2

    def test_detect_work_start_custom_statuses(self):
        """Test detecting work start with custom in-progress statuses."""
        dt = datetime(2024, 1, 2, 10, 0, 0, tzinfo=timezone.utc)

        changelog_items = [
            {"to_value": "Development", "changed_at": dt},
        ]

        result = detect_work_start_from_changelog(
            changelog_items,
            in_progress_statuses=["Development", "Testing"],
        )

        assert result == dt

    def test_detect_work_start_never_started(self):
        """Test when work was never started."""
        dt = datetime(2024, 1, 2, 10, 0, 0, tzinfo=timezone.utc)

        changelog_items = [
            {"to_value": "Open", "changed_at": dt},
            {"to_value": "Backlog", "changed_at": dt},
        ]

        result = detect_work_start_from_changelog(changelog_items)

        assert result is None

    def test_detect_work_start_empty_changelog(self):
        """Test with empty changelog."""
        result = detect_work_start_from_changelog([])

        assert result is None
