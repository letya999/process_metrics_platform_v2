"""Checkpoint task: persist integration_sync_checkpoints row.

Uses the simple in-memory `upsert_sync_checkpoint` helper during unit tests
and delegates to a real DB implementation in integration phase.
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
    """Create and persist a checkpoint entry.

    Args:
        db_conn: DB connection or in-memory dict used for unit tests.
        project: project row. Must contain `tool_integration_id` and
            `project_id` when using a real DB implementation.
        load_info: output from load task.
        entity_type: type of entity checkpointed (default: 'issues').

    Returns:
        The checkpoint dict that was persisted (as stored in the in-memory store).
    """
    now = datetime.now(timezone.utc).replace(microsecond=0)
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # normalize project identifiers for readability and to satisfy line-length
    # constraints
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
