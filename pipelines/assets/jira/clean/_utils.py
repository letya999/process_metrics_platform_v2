"""Shared utilities for the Jira clean layer assets."""

import logging
from typing import Any

from sqlalchemy import text

from pipelines.utils.constants import (
    SPRINT_FIELD_ID_DEFAULT,
)

logger = logging.getLogger(__name__)

_TABLE_EXISTS_CACHE: dict[str, bool] = {}


def _table_exists(conn: Any, schema: str, table: str) -> bool:
    """Check if a table exists in the database with caching."""
    key = f"{schema}.{table}"
    if key in _TABLE_EXISTS_CACHE:
        return _TABLE_EXISTS_CACHE[key]
    result = conn.execute(
        text("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = :schema AND table_name = :table
        )
    """),
        {"schema": schema, "table": table},
    ).scalar()
    _TABLE_EXISTS_CACHE[key] = bool(result)
    return bool(result)


def _get_platform_project_id(conn: Any, project_key: str | None = None) -> str:
    """Get the platform project ID.

    If project_key is given, looks up by external_key.
    Falls back to the oldest active row for backward compatibility with
    single-project setups.
    """
    if project_key:
        result = conn.execute(
            text(
                "SELECT id::text FROM platform.projects"
                " WHERE external_key = :key AND is_active = true"
                " LIMIT 1"
            ),
            {"key": project_key},
        )
        row = result.first()
        if row:
            return row[0]

    # Fallback: oldest active project (deterministic, avoids random LIMIT 1)
    result = conn.execute(
        text(
            "SELECT id::text FROM platform.projects"
            " WHERE is_active = true"
            " ORDER BY created_at"
            " LIMIT 1"
        )
    )
    row = result.first()
    if not row:
        raise RuntimeError(
            "Platform project not found. "
            "Ensure platform.projects has at least one active entry."
        )
    return row[0]


def _detect_sprint_field_id(conn: Any) -> str:
    """Auto-detect sprint custom field ID from raw_jira.fields."""
    try:
        result = conn.execute(text("""
            SELECT id FROM raw_jira.fields
            WHERE schema__custom = 'com.pyxis.greenhopper.jira:gh-sprint'
            LIMIT 1
        """))
        row = result.first()
        if row:
            return row[0]
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to auto-detect sprint field id from raw_jira.fields, "
            "falling back to candidate list: %s",
            exc,
        )

    # Fallback: check candidates in raw_jira.issues columns or use default
    # Note: We don't check existence here to avoid heavy queries, just return
    # the most likely ID based on constants.
    return SPRINT_FIELD_ID_DEFAULT
