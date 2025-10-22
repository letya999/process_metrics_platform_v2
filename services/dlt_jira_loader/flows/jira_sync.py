"""Top-level Prefect flow for Jira sync across multiple projects (Phase 5, Task 16).

This flow accepts a `JiraSyncConfig`, iterates projects, and invokes
`project_sync_subflow` for each. It continues on individual project errors,
returns an aggregate summary with `completed` or `partial_failure` status.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from prefect import flow, get_run_logger
from prefect.exceptions import MissingContextError

from services.dlt_jira_loader.flows.project_sync import project_sync_subflow
from services.dlt_jira_loader.models.config import (
    JiraSyncConfig,
    ProjectWithCredentials,
)
from services.dlt_jira_loader.utils.db import (
    create_pipeline_run,
    fetch_projects_with_credentials,
    finalize_pipeline_run,
)


@flow(name="jira_sync_flow")
def jira_sync_flow(db_conn: Any | None = None, config: JiraSyncConfig | None = None) -> Dict[str, Any]:
    """Run Jira sync for a list of projects defined in `config`.

    Args:
        db_conn: DB handle or in-memory fixtures (unit tests).
        config: JiraSyncConfig with project UUIDs and optional window overrides.

    Returns:
        Aggregate result including per-project summaries and overall status.
    """
    try:
        logger = get_run_logger()
    except MissingContextError:
        logger = logging.getLogger(__name__)

    # Ensure config present (Prefect parameters may be omitted for manual triggers)
    if config is None:
        raise ValueError("config is required")

    # Create pipeline_run entry (in-memory helper for unit/integration tests)
    pipeline_run_id = None
    try:
        pipeline_run_id = create_pipeline_run(
            db_conn if isinstance(db_conn, dict) else {},
            pipeline_name="jira_sync",
            config=config.model_dump()
            if hasattr(config, "model_dump")
            else dict(config),
        )
    except Exception:
        pipeline_run_id = None

    # Discover projects (for now rely on provided db_conn fixtures or minimal utils)
    all_projects = fetch_projects_with_credentials(db_conn if db_conn is not None else {})
    projects_by_id = {
        str(p["project_id"]) if isinstance(p, dict) else str(p.project_id): p
        for p in all_projects
    }

    summaries: List[Dict[str, Any]] = []
    failures = 0

    for project_uuid in config.project_uuids:
        project_key = str(project_uuid)
        proj_raw = projects_by_id.get(project_key)
        if proj_raw is None:
            logger.warning(
                "project not found in discovery", extra={"project_id": project_key}
            )
            failures += 1
            continue

        # Normalize to Pydantic model if dict provided by fixtures
        if isinstance(proj_raw, dict):
            project_model = ProjectWithCredentials(**proj_raw)
        else:
            project_model = proj_raw  # already a ProjectWithCredentials

        try:
            summary = project_sync_subflow(
                db_conn=db_conn, project=project_model, run_config=config
            )
            summaries.append(summary)
        except Exception as exc:  # continue on project failures
            logger.error(
                "project sync failed",
                extra={"project_id": project_key, "error": str(exc)},
            )
            failures += 1

    overall_status = "completed" if failures == 0 else "partial_failure"

    # Finalize pipeline run if created
    try:
        if pipeline_run_id and isinstance(db_conn, dict):
            metrics = {
                "total_projects": len(config.project_uuids),
                "failures": failures,
                "successful": len(summaries),
            }
            finalize_pipeline_run(
                db_conn, pipeline_run_id, status=overall_status, metrics=metrics
            )
    except Exception:
        pass

    return {
        "status": overall_status,
        "total_projects": len(config.project_uuids),
        "failures": failures,
        "summaries": summaries,
    }
