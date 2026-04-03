"""Jira data parsing utilities."""

from datetime import datetime
from typing import Any


def parse_jira_datetime(datetime_str: str | None) -> datetime | None:
    """Parse Jira datetime string to Python datetime.

    Args:
        datetime_str: Jira datetime string in format "2024-01-01T10:00:00.000+0000"

    Returns:
        Parsed datetime or None if input is None/empty
    """
    if not datetime_str:
        return None

    # Jira uses ISO 8601 format with milliseconds
    # Example: "2024-01-01T10:00:00.000+0000"
    try:
        # Try with milliseconds and timezone
        if "+" in datetime_str or datetime_str.endswith("Z"):
            # Remove milliseconds for simpler parsing
            dt_str = datetime_str.replace("Z", "+0000")
            if "." in dt_str:
                base, rest = dt_str.rsplit(".", 1)
                # Extract timezone part
                if "+" in rest:
                    tz_part = "+" + rest.split("+")[1]
                elif "-" in rest:
                    tz_part = "-" + rest.split("-")[1]
                else:
                    tz_part = ""
                dt_str = base + tz_part

            # Parse with timezone
            return datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S%z")
        else:
            # No timezone, parse as naive datetime
            if "." in datetime_str:
                return datetime.strptime(datetime_str, "%Y-%m-%dT%H:%M:%S.%f")
            return datetime.strptime(datetime_str, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None


def parse_jira_issue(raw_issue: dict[str, Any]) -> dict[str, Any]:
    """Parse raw Jira issue data into clean format.

    Args:
        raw_issue: Raw issue data from Jira API

    Returns:
        Parsed issue data with cleaned fields
    """
    fields = raw_issue.get("fields", {})

    # Extract basic fields
    raw_id = raw_issue.get("id")
    parsed = {
        "external_id": str(raw_id) if raw_id is not None else None,
        "external_key": raw_issue.get("key"),
        "summary": fields.get("summary"),
        "description": fields.get("description"),
    }

    # Parse status
    status = fields.get("status", {})
    parsed["status_name"] = status.get("name") if status else None
    parsed["status_category"] = None
    if status and status.get("statusCategory"):
        parsed["status_category"] = status["statusCategory"].get("key")

    # Parse issue type
    issue_type = fields.get("issuetype", {})
    parsed["issue_type_name"] = issue_type.get("name") if issue_type else None
    parsed["issue_type_id"] = issue_type.get("id") if issue_type else None

    # Parse priority
    priority = fields.get("priority", {})
    parsed["priority_name"] = priority.get("name") if priority else None

    # Parse project
    project = fields.get("project", {})
    parsed["project_key"] = project.get("key") if project else None
    parsed["project_id"] = project.get("id") if project else None
    parsed["project_name"] = project.get("name") if project else None

    # Parse dates
    parsed["created_at"] = parse_jira_datetime(fields.get("created"))
    parsed["updated_at"] = parse_jira_datetime(fields.get("updated"))
    parsed["resolved_at"] = parse_jira_datetime(fields.get("resolutiondate"))

    # Parse assignee and reporter
    assignee = fields.get("assignee", {})
    parsed["assignee_account_id"] = assignee.get("accountId") if assignee else None
    parsed["assignee_display_name"] = assignee.get("displayName") if assignee else None

    reporter = fields.get("reporter", {})
    parsed["reporter_account_id"] = reporter.get("accountId") if reporter else None
    parsed["reporter_display_name"] = reporter.get("displayName") if reporter else None

    # Parse story points (field id differs across Jira instances/projects)
    parsed["story_points"] = fields.get("customfield_10016")
    if parsed["story_points"] is None:
        parsed["story_points"] = fields.get("customfield_10036")

    # Parse sprint (if present)
    sprint_field = fields.get("customfield_10020", [])  # Common sprint field
    if sprint_field and isinstance(sprint_field, list) and len(sprint_field) > 0:
        # Get the active sprint (last one in list)
        active_sprint = sprint_field[-1]
        if isinstance(active_sprint, dict):
            parsed["sprint_id"] = active_sprint.get("id")
            parsed["sprint_name"] = active_sprint.get("name")
        elif isinstance(active_sprint, str):
            # Sometimes sprint is returned as string
            parsed["sprint_name"] = active_sprint
            parsed["sprint_id"] = None
    else:
        parsed["sprint_id"] = None
        parsed["sprint_name"] = None

    # Parse labels
    parsed["labels"] = fields.get("labels", [])

    # Parse components
    components = fields.get("components", [])
    parsed["components"] = [c.get("name") for c in components if c.get("name")]

    return parsed


def parse_jira_sprint(raw_sprint: dict[str, Any]) -> dict[str, Any]:
    """Parse raw Jira sprint data into clean format.

    Args:
        raw_sprint: Raw sprint data from Jira API

    Returns:
        Parsed sprint data with cleaned fields
    """
    return {
        "external_id": str(raw_sprint.get("id")),
        "name": raw_sprint.get("name"),
        "state": raw_sprint.get("state"),  # future, active, closed
        "start_date": parse_jira_datetime(raw_sprint.get("startDate")),
        "end_date": parse_jira_datetime(raw_sprint.get("endDate")),
        "complete_date": parse_jira_datetime(raw_sprint.get("completeDate")),
        "goal": raw_sprint.get("goal"),
        "board_id": raw_sprint.get("originBoardId"),
    }


def parse_jira_changelog(raw_changelog: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse raw Jira changelog entry into clean format.

    Args:
        raw_changelog: Raw changelog data from Jira API

    Returns:
        List of parsed changelog items
    """
    items = []
    histories = raw_changelog.get("histories", [])

    for history in histories:
        created = parse_jira_datetime(history.get("created"))
        author = history.get("author", {})
        author_id = author.get("accountId") if author else None

        for item in history.get("items", []):
            items.append(
                {
                    "changed_at": created,
                    "author_account_id": author_id,
                    "field": item.get("field"),
                    "field_type": item.get("fieldtype"),
                    "from_value": item.get("fromString"),
                    "to_value": item.get("toString"),
                    "from_id": item.get("from"),
                    "to_id": item.get("to"),
                }
            )

    return items


def extract_status_changes(
    changelog_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Extract status changes from changelog items.

    Args:
        changelog_items: List of parsed changelog items

    Returns:
        List of status change records
    """
    return [item for item in changelog_items if item.get("field") == "status"]
