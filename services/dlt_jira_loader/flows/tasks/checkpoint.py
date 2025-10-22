"""Checkpoint task: persist integration_sync_checkpoints row.

This remains for backward compatibility and unit tests. New flows may skip
calling it and rely on DLT internal state for incrementality.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from prefect import task

from services.dlt_jira_loader.utils.db import upsert_sync_checkpoint


@task(name="checkpoint.upsert")
def upsert_checkpoint(
    db_conn: Any, project: Any, load_info: Dict[str, Any], entity_type: str = "issues"
) -> Dict[str, Any]:
    """Create and persist a checkpoint entry (in-memory or real DB in future).

    Returns the checkpoint dict for unit tests and callers who need the value.
    """
    now = datetime.now(timezone.utc).replace(microsecond=0)
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # normalize project identifiers
    tool_integration_id = getattr(project, "tool_integration_id", None)
    if not tool_integration_id:
        tool_integration_id = project.get("tool_integration_id")

    project_id = getattr(project, "project_id", None)
    if not project_id:
        project_id = project.get("project_id")

    checkpoint = {
        "tool_integration_id": tool_integration_id,
        "project_id": project_id,
        "entity_type": entity_type,
        "last_synced_at": load_info.get("last_synced_at", now_iso),
        "sync_metadata": {"rows": load_info.get("rows_loaded_by_resource", {})},
    }

    upsert_sync_checkpoint(db_conn, checkpoint)

    return checkpoint
