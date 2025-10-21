"""Per-project orchestration subflow for Jira sync (Phase 5, Task 15).

The subflow coordinates:
  1) Determine sync window for the project
  2) Prepare DLT resources (3 sequential passes for issues are abstracted
     inside the source; here we keep a single preparation step)
  3) Load resources with DLT (or simulate when DLT is disabled)
  4) Validate the load
  5) Write/update checkpoint

Returns a small summary dict for the parent flow to aggregate.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from prefect import flow, get_run_logger
from prefect.exceptions import MissingContextError

from services.dlt_jira_loader.flows.tasks.checkpoint import upsert_checkpoint
from services.dlt_jira_loader.flows.tasks.extract import prepare_resources
from services.dlt_jira_loader.flows.tasks.load import run_load
from services.dlt_jira_loader.flows.tasks.sync_window import determine_window
from services.dlt_jira_loader.flows.tasks.validation import validate_load
from services.dlt_jira_loader.models.config import (
    JiraSyncConfig,
    ProjectWithCredentials,
)


@flow(name="project_sync_subflow")
def project_sync_subflow(
    db_conn: Any,
    project: ProjectWithCredentials,
    run_config: JiraSyncConfig,
) -> Dict[str, Any]:
    """Run sync for a single project and return a summary.

    Args:
        db_conn: DB handle or in-memory fixture used by tasks.
        project: project row with credentials.
        run_config: top-level run configuration.

    Returns:
        Summary dict with project id, status and load metrics.
    """
    try:
        logger = get_run_logger()
    except MissingContextError:
        logger = logging.getLogger(__name__)

    window = determine_window(run_config)
    logger.info(
        "sync window determined",
        extra={"project": project.external_key, **window},
    )

    resources = prepare_resources(
        project=project, date_from=window["date_from"], date_to=window["date_to"]
    )

    load_info = run_load(
        project=project, resources=resources, dataset_name=run_config.dataset_name
    )
    validation = validate_load(load_info)

    # checkpoint for issues entity as a minimal invariant for now
    checkpoint = upsert_checkpoint(
        db_conn=db_conn,
        project={"tool_integration_id": None, "project_id": project.project_id},
        load_info=load_info,
        entity_type="issues",
    )

    status = "ok" if validation.get("status") == "ok" else "warning"

    return {
        "project_id": str(project.project_id),
        "project_external_key": project.external_key,
        "status": status,
        "window": window,
        "load_info": load_info,
        "validation": validation,
        "checkpoint": checkpoint,
    }
