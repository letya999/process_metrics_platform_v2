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

from services.dlt_jira_loader.flows.tasks.extract import prepare_resources
from services.dlt_jira_loader.flows.tasks.load import run_load
from services.dlt_jira_loader.flows.tasks.sync_window import determine_window
from services.dlt_jira_loader.flows.tasks.validation import validate_load
from services.dlt_jira_loader.models.config import (
    JiraSyncConfig,
    ProjectWithCredentials,
)
from services.dlt_jira_loader.utils.db import (
    resolve_integration_secret,
    record_project_run_metrics,
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

    # Inject resolved secret into credentials without persisting it.
    # Expect project.credentials to contain tool_integration_id, instance_url, user_email
    secret_token = None
    try:
        ti_id = (
            project.credentials.get("tool_integration_id")
            if isinstance(project.credentials, dict)
            else None
        )
        if ti_id:
            secret_token = resolve_integration_secret(str(ti_id))
    except Exception:
        secret_token = None

    overrides: Dict[str, Any] = {}
    if secret_token:
        overrides["api_token"] = secret_token

    resources = prepare_resources(
        project=project,
        date_from=window["date_from"],
        date_to=window["date_to"],
        config_overrides=overrides or None,
    )

    load_info = run_load(
        project=project, resources=resources, dataset_name=run_config.dataset_name
    )
    validation = validate_load(load_info)

    status = "ok" if validation.get("status") == "ok" else "warning"

    # optional metrics insert (best-effort; non-blocking)
    try:
        record_project_run_metrics(
            pipeline_name="jira_sync",
            project_id=str(project.project_id),
            window=window,
            load_info=load_info,
            status=status,
        )
    except Exception:
        pass

    return {
        "project_id": str(project.project_id),
        "project_external_key": project.external_key,
        "status": status,
        "window": window,
        "load_info": load_info,
        "validation": validation,
    }
