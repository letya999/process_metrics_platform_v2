"""Tests for metrics calculation utilities."""

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
        created = datetime(2024, 1, 1, 10, 0, 0)
        resolved = datetime(2024, 1, 3, 10, 0, 0)

        result = calculate_lead_time(created, resolved)

        assert result["lead_time_days"] == 2.0
        assert result["lead_time_hours"] == 48.0

    def test_calculate_lead_time_with_hours(self):
        """Test lead time with partial days."""
        created = datetime(2024, 1, 1, 0, 0, 0)
        resolved = datetime(2024, 1, 1, 12, 0, 0)

        result = calculate_lead_time(created, resolved)

        assert result["lead_time_days"] == 0.5
        assert result["lead_time_hours"] == 12.0

    def test_calculate_lead_time_none_created(self):
        """Test with None created_at."""
        result = calculate_lead_time(None, datetime(2024, 1, 1))

        assert result["lead_time_days"] is None
        assert result["lead_time_hours"] is None

    def test_calculate_lead_time_none_resolved(self):
        """Test with None resolved_at."""
        result = calculate_lead_time(datetime(2024, 1, 1), None)

        assert result["lead_time_days"] is None
        assert result["lead_time_hours"] is None

    def test_calculate_lead_time_both_none(self):
        """Test with both dates None."""
        result = calculate_lead_time(None, None)

        assert result["lead_time_days"] is None
        assert result["lead_time_hours"] is None

    def test_calculate_lead_time_timezone_aware(self):
        """Test with timezone-aware datetimes."""
        created = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        resolved = datetime(2024, 1, 2, 10, 0, 0, tzinfo=timezone.utc)

        result = calculate_lead_time(created, resolved)

        assert result["lead_time_days"] == 1.0
        assert result["lead_time_hours"] == 24.0

    def test_calculate_lead_time_mixed_timezone(self):
        """Test with mixed timezone-aware and naive datetimes."""
        created = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        resolved = datetime(2024, 1, 2, 10, 0, 0)  # naive

        result = calculate_lead_time(created, resolved)

        assert result["lead_time_days"] == 1.0
        assert result["lead_time_hours"] == 24.0


class TestCalculateCycleTime:
    """Tests for calculate_cycle_time function."""

    def test_calculate_cycle_time_basic(self):
        """Test basic cycle time calculation."""
        started = datetime(2024, 1, 2, 10, 0, 0)
        resolved = datetime(2024, 1, 4, 10, 0, 0)

        result = calculate_cycle_time(started, resolved)

        assert result["cycle_time_days"] == 2.0
        assert result["cycle_time_hours"] == 48.0

    def test_calculate_cycle_time_none_started(self):
        """Test with None started_at."""
        result = calculate_cycle_time(None, datetime(2024, 1, 1))

        assert result["cycle_time_days"] is None
        assert result["cycle_time_hours"] is None

    def test_calculate_cycle_time_none_resolved(self):
        """Test with None resolved_at."""
        result = calculate_cycle_time(datetime(2024, 1, 1), None)

        assert result["cycle_time_days"] is None
        assert result["cycle_time_hours"] is None

    def test_calculate_cycle_time_same_day(self):
        """Test cycle time within same day."""
        started = datetime(2024, 1, 1, 9, 0, 0)
        resolved = datetime(2024, 1, 1, 17, 0, 0)

        result = calculate_cycle_time(started, resolved)

        assert result["cycle_time_hours"] == 8.0
        assert abs(result["cycle_time_days"] - (8.0 / 24.0)) < 0.001


class TestCalculateSprintVelocity:
    """Tests for calculate_sprint_velocity function."""

    def test_velocity_all_done(self):
        """Test velocity when all issues are done."""
        issues = [
            {"status_name": "Done", "story_points": 3},
            {"status_name": "Done", "story_points": 5},
            {"status_name": "Done", "story_points": 2},
        ]

        result = calculate_sprint_velocity(issues)

        assert result["total_issues"] == 3
        assert result["completed_issues"] == 3
        assert result["completion_rate_pct"] == 100.0
        assert result["total_story_points"] == 10.0
        assert result["completed_story_points"] == 10.0
        assert result["story_points_completion_rate_pct"] == 100.0

    def test_velocity_partial_completion(self):
        """Test velocity with partial completion."""
        issues = [
            {"status_name": "Done", "story_points": 3},
            {"status_name": "In Progress", "story_points": 5},
            {"status_name": "To Do", "story_points": 2},
        ]

        result = calculate_sprint_velocity(issues)

        assert result["total_issues"] == 3
        assert result["completed_issues"] == 1
        assert result["completion_rate_pct"] == pytest.approx(33.33, rel=0.01)
        assert result["total_story_points"] == 10.0
        assert result["completed_story_points"] == 3.0
        assert result["story_points_completion_rate_pct"] == 30.0

    def test_velocity_no_issues(self):
        """Test velocity with empty issue list."""
        result = calculate_sprint_velocity([])

        assert result["total_issues"] == 0
        assert result["completed_issues"] == 0
        assert result["completion_rate_pct"] == 0.0
        assert result["total_story_points"] == 0.0
        assert result["completed_story_points"] == 0.0

    def test_velocity_no_story_points(self):
        """Test velocity when issues have no story points."""
        issues = [
            {"status_name": "Done", "story_points": None},
            {"status_name": "Done"},  # missing story_points
        ]

        result = calculate_sprint_velocity(issues)

        assert result["total_issues"] == 2
        assert result["completed_issues"] == 2
        assert result["total_story_points"] == 0.0
        assert result["completed_story_points"] == 0.0

    def test_velocity_custom_done_statuses(self):
        """Test velocity with custom done statuses."""
        issues = [
            {"status_name": "Completed", "story_points": 3},
            {"status_name": "Shipped", "story_points": 5},
            {"status_name": "In Progress", "story_points": 2},
        ]

        result = calculate_sprint_velocity(
            issues, done_statuses=["Completed", "Shipped"]
        )

        assert result["completed_issues"] == 2
        assert result["completed_story_points"] == 8.0

    def test_velocity_multiple_done_statuses(self):
        """Test velocity recognizes multiple done status variants."""
        issues = [
            {"status_name": "Done", "story_points": 2},
            {"status_name": "Closed", "story_points": 3},
            {"status_name": "Resolved", "story_points": 4},
            {"status_name": "Open", "story_points": 1},
        ]

        result = calculate_sprint_velocity(issues)

        assert result["completed_issues"] == 3
        assert result["completed_story_points"] == 9.0


class TestCalculateThroughput:
    """Tests for calculate_throughput function."""

    def test_throughput_basic(self):
        """Test basic throughput calculation."""
        issues = [
            {"resolved_at": datetime(2024, 1, 2, 10, 0)},
            {"resolved_at": datetime(2024, 1, 2, 15, 0)},
            {"resolved_at": datetime(2024, 1, 3, 12, 0)},
        ]
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 3, 23, 59, 59)  # End of day

        result = calculate_throughput(issues, start, end)

        assert result["total_issues_completed"] == 3
        assert result["days_in_range"] == 3
        assert result["avg_daily_throughput"] == 1.0
        assert result["by_date"]["2024-01-02"] == 2
        assert result["by_date"]["2024-01-03"] == 1

    def test_throughput_no_issues(self):
        """Test throughput with no issues."""
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 7)

        result = calculate_throughput([], start, end)

        assert result["total_issues_completed"] == 0
        assert result["days_in_range"] == 7
        assert result["avg_daily_throughput"] == 0.0
        assert result["by_date"] == {}

    def test_throughput_filters_by_date_range(self):
        """Test that throughput filters issues outside range."""
        issues = [
            {"resolved_at": datetime(2024, 1, 1, 10, 0)},  # in range
            {"resolved_at": datetime(2024, 1, 3, 10, 0)},  # in range
            {"resolved_at": datetime(2024, 1, 10, 10, 0)},  # out of range
        ]
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 5)

        result = calculate_throughput(issues, start, end)

        assert result["total_issues_completed"] == 2

    def test_throughput_handles_none_resolved_at(self):
        """Test throughput ignores issues without resolved_at."""
        issues = [
            {"resolved_at": datetime(2024, 1, 2, 10, 0)},
            {"resolved_at": None},
            {"status": "Open"},  # no resolved_at key
        ]
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 3)

        result = calculate_throughput(issues, start, end)

        assert result["total_issues_completed"] == 1

    def test_throughput_max_min_daily(self):
        """Test max and min daily throughput."""
        issues = [
            {"resolved_at": datetime(2024, 1, 1, 10, 0)},
            {"resolved_at": datetime(2024, 1, 1, 11, 0)},
            {"resolved_at": datetime(2024, 1, 1, 12, 0)},
            {"resolved_at": datetime(2024, 1, 2, 10, 0)},
        ]
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 3)

        result = calculate_throughput(issues, start, end)

        assert result["max_daily"] == 3
        assert result["min_daily"] == 1


class TestCalculateLeadTimePercentiles:
    """Tests for calculate_lead_time_percentiles function."""

    def test_percentiles_basic(self):
        """Test basic percentile calculation."""
        lead_times = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]

        result = calculate_lead_time_percentiles(lead_times)

        assert result["p50"] is not None
        assert result["p75"] is not None
        assert result["p85"] is not None
        assert result["p95"] is not None
        assert result["avg"] == 5.5

    def test_percentiles_empty_list(self):
        """Test percentiles with empty list."""
        result = calculate_lead_time_percentiles([])

        assert result["p50"] is None
        assert result["p75"] is None
        assert result["p85"] is None
        assert result["p95"] is None
        assert result["avg"] is None

    def test_percentiles_single_value(self):
        """Test percentiles with single value."""
        result = calculate_lead_time_percentiles([5.0])

        assert result["p50"] == 5.0
        assert result["p75"] == 5.0
        assert result["p95"] == 5.0
        assert result["avg"] == 5.0

    def test_percentiles_two_values(self):
        """Test percentiles with two values."""
        result = calculate_lead_time_percentiles([2.0, 8.0])

        assert result["avg"] == 5.0
        # p50 should be between 2 and 8
        assert 2.0 <= result["p50"] <= 8.0

    def test_percentiles_unsorted_input(self):
        """Test that function handles unsorted input."""
        lead_times = [5.0, 1.0, 9.0, 3.0, 7.0]

        result = calculate_lead_time_percentiles(lead_times)

        assert result["avg"] == 5.0
        assert result["p50"] == 5.0  # median of sorted [1, 3, 5, 7, 9]


class TestDetectWorkStartFromChangelog:
    """Tests for detect_work_start_from_changelog function."""

    def test_detect_work_start_basic(self):
        """Test basic work start detection."""
        changelog = [
            {
                "field": "status",
                "to_value": "In Progress",
                "changed_at": datetime(2024, 1, 2, 10, 0, 0),
            },
            {
                "field": "status",
                "to_value": "Done",
                "changed_at": datetime(2024, 1, 5, 10, 0, 0),
            },
        ]

        result = detect_work_start_from_changelog(changelog)

        assert result == datetime(2024, 1, 2, 10, 0, 0)

    def test_detect_work_start_finds_earliest(self):
        """Test that earliest in-progress status is returned."""
        changelog = [
            {
                "field": "status",
                "to_value": "In Review",
                "changed_at": datetime(2024, 1, 5, 10, 0, 0),
            },
            {
                "field": "status",
                "to_value": "In Progress",
                "changed_at": datetime(2024, 1, 2, 10, 0, 0),
            },
        ]

        result = detect_work_start_from_changelog(changelog)

        assert result == datetime(2024, 1, 2, 10, 0, 0)

    def test_detect_work_start_no_progress_status(self):
        """Test when no in-progress status exists."""
        changelog = [
            {
                "field": "status",
                "to_value": "To Do",
                "changed_at": datetime(2024, 1, 1, 10, 0, 0),
            },
            {
                "field": "status",
                "to_value": "Done",
                "changed_at": datetime(2024, 1, 5, 10, 0, 0),
            },
        ]

        result = detect_work_start_from_changelog(changelog)

        assert result is None

    def test_detect_work_start_empty_changelog(self):
        """Test with empty changelog."""
        result = detect_work_start_from_changelog([])

        assert result is None

    def test_detect_work_start_custom_statuses(self):
        """Test with custom in-progress statuses."""
        changelog = [
            {
                "field": "status",
                "to_value": "Coding",
                "changed_at": datetime(2024, 1, 2, 10, 0, 0),
            },
            {
                "field": "status",
                "to_value": "Done",
                "changed_at": datetime(2024, 1, 5, 10, 0, 0),
            },
        ]

        result = detect_work_start_from_changelog(
            changelog, in_progress_statuses=["Coding", "Testing"]
        )

        assert result == datetime(2024, 1, 2, 10, 0, 0)

    def test_detect_work_start_ignores_missing_changed_at(self):
        """Test that items without changed_at are ignored."""
        changelog = [
            {
                "field": "status",
                "to_value": "In Progress",
                # no changed_at
            },
            {
                "field": "status",
                "to_value": "In Progress",
                "changed_at": datetime(2024, 1, 3, 10, 0, 0),
            },
        ]

        result = detect_work_start_from_changelog(changelog)

        assert result == datetime(2024, 1, 3, 10, 0, 0)
