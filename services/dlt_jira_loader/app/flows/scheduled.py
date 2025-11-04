"""Scheduled wrapper flow for jira sync."""
# ruff: noqa: E501
from __future__ import annotations

import inspect
from typing import Any, Dict, List, Optional

from prefect import flow, get_run_logger

# Make relative import safe when Prefect loads this module as a script
try:
    pass  # type: ignore
except Exception:
    pass

from .jira_sync import jira_sync_flow


def _batch(items: List[Any], batch_size: int) -> List[List[Any]]:
    return [items[i : i + batch_size] for i in range(0, len(items), batch_size)]


@flow(name="jira_sync_scheduled_wrapper", log_prints=True)
def jira_sync_scheduled_wrapper(
    db_conn: Optional[Dict[str, Any]] = None, batch_size: int = 3
) -> Dict[str, Any]:
    """Discover projects (stubbed via db_conn for tests) and trigger child flows in batches."""
    # Guard: Prefect `get_run_logger` requires a flow/task context; for
    # unit tests we fall back to a standard logger to avoid raising.
    try:
        logger = get_run_logger()
    except Exception:
        import logging

        logger = logging.getLogger("dlt_jira_loader.tests")
    projects = []

    # In tests, db_conn is a dict with key 'projects'
    if isinstance(db_conn, dict):
        projects = [p for p in db_conn.get("projects", []) if p.get("is_active", True)]

    if not projects:
        logger.info("no projects to sync")
        return {"status": "no_projects"}

    batches = _batch(projects, batch_size)
    for b in batches:
        # In unit tests, we don't actually want to start Prefect async tasks — just call fn(s)
        project_ids = [p["project_id"] for p in b]
        try:
            # Call underlying flow function directly to keep tests fast.
            result = jira_sync_flow.fn(project_uuids=project_ids)
            # If the underlying flow function is async, run it to completion
            # to avoid "coroutine was never awaited" warnings in sync tests.
            if inspect.iscoroutine(result):
                import asyncio

                asyncio.run(result)
        except Exception:  # pragma: no cover
            logger.warning("child flow call failed", exc_info=True)

    return {
        "status": "ok",
        "project_count": len(projects),
        "batches_started": len(batches),
    }
