"""Shared utilities for the Jira clean layer assets."""

from typing import Any

from sqlalchemy import text


def _get_platform_project_id(conn: Any) -> str:
    """Get the platform project ID dynamically."""
    result = conn.execute(text("SELECT id::text FROM platform.projects LIMIT 1"))
    row = result.first()
    if not row:
        raise RuntimeError(
            "Platform project not found. "
            "Ensure platform.projects has at least one entry."
        )
    return row[0]


def _detect_sprint_field_id(conn: Any) -> str:
    """Auto-detect sprint custom field ID from raw_jira.fields."""
    try:
        result = conn.execute(
            text(
                """
            SELECT id FROM raw_jira.fields
            WHERE schema__custom = 'com.pyxis.greenhopper.jira:gh-sprint'
            LIMIT 1
        """
            )
        )
        row = result.first()
        if row:
            return row[0]
    except Exception:  # noqa: S110
        pass
    # Fallback to standard customfield_10020
    return "customfield_10020"
