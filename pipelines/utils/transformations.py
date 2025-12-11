"""Transformation utilities for raw → clean data layer."""

from datetime import datetime
from typing import Any

from pipelines.utils import parse_jira_changelog, parse_jira_datetime, parse_jira_issue


def transform_raw_issue_to_clean(
    raw_issue: dict[str, Any],
    integration_id: str | None = None,
) -> dict[str, Any]:
    """Transform a raw Jira issue to clean format.

    Args:
        raw_issue: Raw issue data from Jira API
        integration_id: ID of the tool integration

    Returns:
        Clean issue data ready for database insertion
    """
    parsed = parse_jira_issue(raw_issue)

    return {
        "external_id": parsed["external_id"],
        "external_key": parsed["external_key"],
        "integration_id": integration_id,
        "project_external_id": parsed.get("project_id"),
        "project_external_key": parsed.get("project_key"),
        "summary": parsed["summary"],
        "description": parsed.get("description"),
        "status_name": parsed["status_name"],
        "status_category": parsed["status_category"],
        "issue_type_name": parsed["issue_type_name"],
        "issue_type_id": parsed["issue_type_id"],
        "priority_name": parsed.get("priority_name"),
        "assignee_account_id": parsed.get("assignee_account_id"),
        "assignee_display_name": parsed.get("assignee_display_name"),
        "reporter_account_id": parsed.get("reporter_account_id"),
        "reporter_display_name": parsed.get("reporter_display_name"),
        "labels": parsed.get("labels", []),
        "components": parsed.get("components", []),
        "story_points": parsed.get("story_points"),
        "sprint_id": parsed.get("sprint_id"),
        "sprint_name": parsed.get("sprint_name"),
        "created_at": parsed["created_at"],
        "updated_at": parsed["updated_at"],
        "resolved_at": parsed["resolved_at"],
    }


def transform_raw_issues_batch(
    raw_issues: list[dict[str, Any]],
    integration_id: str | None = None,
) -> list[dict[str, Any]]:
    """Transform a batch of raw issues to clean format.

    Args:
        raw_issues: List of raw issue data from Jira API
        integration_id: ID of the tool integration

    Returns:
        List of clean issue data
    """
    return [transform_raw_issue_to_clean(issue, integration_id) for issue in raw_issues]


def transform_raw_sprint_to_clean(
    raw_sprint: dict[str, Any],
    board_id: int | str | None = None,
) -> dict[str, Any]:
    """Transform a raw Jira sprint to clean format.

    Args:
        raw_sprint: Raw sprint data from Jira API
        board_id: ID of the board (if not in raw data)

    Returns:
        Clean sprint data ready for database insertion
    """
    external_id = str(raw_sprint.get("id", ""))
    name = raw_sprint.get("name", "")
    state = raw_sprint.get("state", "")
    goal = raw_sprint.get("goal")

    start_date = parse_jira_datetime(raw_sprint.get("startDate"))
    end_date = parse_jira_datetime(raw_sprint.get("endDate"))
    complete_date = parse_jira_datetime(raw_sprint.get("completeDate"))

    resolved_board_id = raw_sprint.get("originBoardId") or board_id

    return {
        "external_id": external_id,
        "name": name,
        "state": state,
        "goal": goal,
        "board_id": resolved_board_id,
        "start_date": start_date,
        "end_date": end_date,
        "complete_date": complete_date,
    }


def transform_changelog_to_status_transitions(
    issue_key: str,
    raw_changelog: dict[str, Any],
) -> list[dict[str, Any]]:
    """Transform raw changelog to status transition records.

    Args:
        issue_key: The issue key (e.g., "PROJ-123")
        raw_changelog: Raw changelog data from Jira API

    Returns:
        List of status transition records
    """
    changelog_items = parse_jira_changelog(raw_changelog)

    transitions = []
    for item in changelog_items:
        if item.get("field") == "status":
            transitions.append(
                {
                    "issue_key": issue_key,
                    "from_status": item.get("from_value"),
                    "to_status": item.get("to_value"),
                    "changed_at": item.get("changed_at"),
                    "changed_by": item.get("author_id"),
                }
            )

    return transitions


def validate_clean_issue(issue: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate a clean issue has required fields.

    Args:
        issue: Clean issue data

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    errors = []

    required_fields = ["external_id", "external_key", "summary"]
    for field in required_fields:
        if not issue.get(field):
            errors.append(f"Missing required field: {field}")

    # Validate external_id format
    ext_id = issue.get("external_id")
    if ext_id and not isinstance(ext_id, str):
        errors.append("external_id must be a string")

    # Validate dates are datetime objects if present
    date_fields = ["created_at", "updated_at", "resolved_at"]
    for field in date_fields:
        value = issue.get(field)
        if value is not None and not isinstance(value, datetime):
            errors.append(f"{field} must be a datetime object")

    # Validate story_points is numeric if present
    sp = issue.get("story_points")
    if sp is not None and not isinstance(sp, (int, float)):
        errors.append("story_points must be numeric")

    return (len(errors) == 0, errors)


def deduplicate_issues(
    issues: list[dict[str, Any]],
    key_field: str = "external_key",
) -> list[dict[str, Any]]:
    """Deduplicate issues by key, keeping the most recent.

    Args:
        issues: List of issue data
        key_field: Field to use as unique key

    Returns:
        Deduplicated list of issues
    """
    seen: dict[str, dict[str, Any]] = {}

    for issue in issues:
        key = issue.get(key_field)
        if not key:
            continue

        existing = seen.get(key)
        if existing is None:
            seen[key] = issue
        else:
            # Keep the one with more recent updated_at
            existing_updated = existing.get("updated_at")
            new_updated = issue.get("updated_at")

            if new_updated and (not existing_updated or new_updated > existing_updated):
                seen[key] = issue

    return list(seen.values())


def enrich_issue_with_lead_time(
    issue: dict[str, Any],
) -> dict[str, Any]:
    """Enrich issue with calculated lead time.

    Args:
        issue: Clean issue data with created_at and resolved_at

    Returns:
        Issue with lead_time_days and lead_time_hours added
    """
    from pipelines.utils.metrics import calculate_lead_time

    created_at = issue.get("created_at")
    resolved_at = issue.get("resolved_at")

    lead_time = calculate_lead_time(created_at, resolved_at)

    return {
        **issue,
        "lead_time_days": lead_time["lead_time_days"],
        "lead_time_hours": lead_time["lead_time_hours"],
    }
