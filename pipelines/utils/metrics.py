"""Metrics calculation utilities."""

from datetime import datetime
from typing import Any


def calculate_lead_time(
    created_at: datetime | None,
    resolved_at: datetime | None,
) -> dict[str, float | None]:
    """Calculate lead time between creation and resolution.

    Args:
        created_at: Issue creation datetime
        resolved_at: Issue resolution datetime

    Returns:
        Dictionary with lead_time_days and lead_time_hours
    """
    if not created_at or not resolved_at:
        return {"lead_time_days": None, "lead_time_hours": None}

    # Ensure both are comparable (handle timezone-aware vs naive)
    if created_at.tzinfo is not None and resolved_at.tzinfo is None:
        resolved_at = resolved_at.replace(tzinfo=created_at.tzinfo)
    elif created_at.tzinfo is None and resolved_at.tzinfo is not None:
        created_at = created_at.replace(tzinfo=resolved_at.tzinfo)

    delta = resolved_at - created_at
    total_seconds = delta.total_seconds()

    return {
        "lead_time_days": total_seconds / 86400.0,  # 86400 seconds in a day
        "lead_time_hours": total_seconds / 3600.0,  # 3600 seconds in an hour
    }


def calculate_cycle_time(
    started_at: datetime | None,
    resolved_at: datetime | None,
) -> dict[str, float | None]:
    """Calculate cycle time between start of work and resolution.

    Args:
        started_at: When work started (e.g., moved to "In Progress")
        resolved_at: Issue resolution datetime

    Returns:
        Dictionary with cycle_time_days and cycle_time_hours
    """
    if not started_at or not resolved_at:
        return {"cycle_time_days": None, "cycle_time_hours": None}

    # Ensure both are comparable
    if started_at.tzinfo is not None and resolved_at.tzinfo is None:
        resolved_at = resolved_at.replace(tzinfo=started_at.tzinfo)
    elif started_at.tzinfo is None and resolved_at.tzinfo is not None:
        started_at = started_at.replace(tzinfo=resolved_at.tzinfo)

    delta = resolved_at - started_at
    total_seconds = delta.total_seconds()

    return {
        "cycle_time_days": total_seconds / 86400.0,
        "cycle_time_hours": total_seconds / 3600.0,
    }


def calculate_sprint_velocity(
    issues: list[dict[str, Any]],
    done_statuses: list[str] | None = None,
) -> dict[str, Any]:
    """Calculate sprint velocity metrics.

    Args:
        issues: List of issues in the sprint
        done_statuses: List of status names that indicate completion

    Returns:
        Dictionary with velocity metrics
    """
    if done_statuses is None:
        done_statuses = ["Done", "Closed", "Resolved"]

    total_issues = len(issues)
    completed_issues = 0
    total_story_points = 0.0
    completed_story_points = 0.0

    for issue in issues:
        status = issue.get("status_name", "")
        story_points = issue.get("story_points") or 0

        if isinstance(story_points, (int, float)):
            total_story_points += story_points

        if status in done_statuses:
            completed_issues += 1
            if isinstance(story_points, (int, float)):
                completed_story_points += story_points

    completion_rate = (
        (completed_issues / total_issues * 100) if total_issues > 0 else 0.0
    )

    return {
        "total_issues": total_issues,
        "completed_issues": completed_issues,
        "completion_rate_pct": round(completion_rate, 2),
        "total_story_points": total_story_points,
        "completed_story_points": completed_story_points,
        "story_points_completion_rate_pct": (
            round(completed_story_points / total_story_points * 100, 2)
            if total_story_points > 0
            else 0.0
        ),
    }


def calculate_throughput(
    issues: list[dict[str, Any]],
    start_date: datetime,
    end_date: datetime,
) -> dict[str, Any]:
    """Calculate throughput metrics for a date range.

    Args:
        issues: List of resolved issues with resolved_at datetime
        start_date: Start of the period
        end_date: End of the period

    Returns:
        Dictionary with throughput metrics
    """
    # Filter issues resolved in the date range
    resolved_in_range = []
    for issue in issues:
        resolved_at = issue.get("resolved_at")
        if resolved_at:
            # Normalize timezone
            if start_date.tzinfo is not None and resolved_at.tzinfo is None:
                resolved_at = resolved_at.replace(tzinfo=start_date.tzinfo)
            elif start_date.tzinfo is None and resolved_at.tzinfo is not None:
                start_date = start_date.replace(tzinfo=resolved_at.tzinfo)
                end_date = end_date.replace(tzinfo=resolved_at.tzinfo)

            if start_date <= resolved_at <= end_date:
                resolved_in_range.append(issue)

    # Calculate days in range
    days_in_range = (end_date - start_date).days + 1

    # Group by date
    by_date: dict[str, int] = {}
    for issue in resolved_in_range:
        resolved_at = issue.get("resolved_at")
        if resolved_at:
            date_str = resolved_at.strftime("%Y-%m-%d")
            by_date[date_str] = by_date.get(date_str, 0) + 1

    total_completed = len(resolved_in_range)
    avg_daily = total_completed / days_in_range if days_in_range > 0 else 0

    return {
        "total_issues_completed": total_completed,
        "days_in_range": days_in_range,
        "avg_daily_throughput": round(avg_daily, 2),
        "by_date": by_date,
        "max_daily": max(by_date.values()) if by_date else 0,
        "min_daily": min(by_date.values()) if by_date else 0,
    }


def calculate_lead_time_percentiles(
    lead_times: list[float],
) -> dict[str, float | None]:
    """Calculate lead time percentiles.

    Args:
        lead_times: List of lead time values in days

    Returns:
        Dictionary with percentile values
    """
    if not lead_times:
        return {
            "p50": None,
            "p75": None,
            "p85": None,
            "p95": None,
            "avg": None,
        }

    sorted_times = sorted(lead_times)
    n = len(sorted_times)

    def percentile(p: float) -> float:
        k = (n - 1) * p / 100
        f = int(k)
        c = f + 1
        if c >= n:
            return sorted_times[-1]
        return sorted_times[f] + (k - f) * (sorted_times[c] - sorted_times[f])

    return {
        "p50": round(percentile(50), 2),
        "p75": round(percentile(75), 2),
        "p85": round(percentile(85), 2),
        "p95": round(percentile(95), 2),
        "avg": round(sum(sorted_times) / n, 2),
    }


def detect_work_start_from_changelog(
    changelog_items: list[dict[str, Any]],
    in_progress_statuses: list[str] | None = None,
) -> datetime | None:
    """Detect when work started from changelog.

    Args:
        changelog_items: List of changelog items (status changes)
        in_progress_statuses: Statuses that indicate work has started

    Returns:
        Datetime when issue first moved to an in-progress status
    """
    if in_progress_statuses is None:
        in_progress_statuses = ["In Progress", "In Development", "In Review"]

    # Sort by changed_at
    sorted_items = sorted(
        [i for i in changelog_items if i.get("changed_at")],
        key=lambda x: x["changed_at"],
    )

    for item in sorted_items:
        if item.get("to_value") in in_progress_statuses:
            return item.get("changed_at")

    return None
