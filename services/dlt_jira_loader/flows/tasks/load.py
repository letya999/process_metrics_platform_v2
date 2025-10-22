"""DLT load task used by Prefect flows.

This task is intentionally conservative: by default it does not perform a
real DLT run (heavy). To enable real runs (integration), set environment
variable `DLT_ENABLE_REAL_RUN=1` in the worker environment.

Task returns a lightweight `LoadInfo` dict with summary metrics consumed by
validation and checkpoint tasks.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, Iterable

from prefect import task

try:
    import dlt
    from dlt.destinations import postgres as dlt_postgres  # type: ignore
except Exception:  # pragma: no cover - allow tests to run without dlt installed
    dlt = None
    dlt_postgres = None  # type: ignore


@task(name="load.run_pipeline")
def run_load(
    project: Any,
    resources: Dict[str, Iterable],
    dataset_name: str = "raw_jira_cloud_dlt",
) -> Dict[str, Any]:
    """Run (or simulate) DLT load for provided resources.

    Args:
        project: project row (used for naming/metadata).
        resources: mapping of resource name to DLT resource callables.
        dataset_name: target dataset/schema for DLT.

    Returns:
        LoadInfo dict with at least `rows_loaded_by_resource` and `last_synced_at`.
    """
    # produce a timezone-aware UTC timestamp and format as Z-suffixed
    now = datetime.now(timezone.utc).replace(microsecond=0)
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    enable_real = os.getenv("DLT_ENABLE_REAL_RUN") == "1"

    rows_by_resource: Dict[str, int] = {}

    if enable_real and dlt is not None and dlt_postgres is not None:
        # Real DLT run: create a pipeline and run resources. This path runs only
        # in integration environments where DLT is expected to be installed and
        # network access to Jira is available.
        pipeline_name = f"jira_{getattr(project, 'external_key', 'project')}"

        # Configure Postgres destination from env; fallback to simulation if missing
        db_host = os.getenv("DB_HOST")
        db_name = os.getenv("DB_NAME")
        db_user = os.getenv("DB_USER")
        db_password = os.getenv("DB_PASSWORD")

        if db_host and db_name and db_user and db_password:
            pg_url = f"postgresql://{db_user}:{db_password}@{db_host}/{db_name}"
            destination = dlt_postgres(credentials=pg_url)
            pipeline = dlt.pipeline(
                pipeline_name=pipeline_name,
                destination=destination,
                dataset_name=dataset_name,
            )
        else:
            # Missing DB settings -> run in simulation mode
            enable_real = False
        for name, resource_callable in resources.items():
            try:
                run_info = pipeline.run(source=resource_callable)
                # Best-effort extract row count if available in run_info
                rows_by_resource[name] = int(getattr(run_info, "rows", 0) or 0)
            except Exception:
                rows_by_resource[name] = 0
    if not enable_real:
        # Simulation/demo mode used by unit tests: do not call network or
        # DLT heavy code.
        for name in resources.keys():
            rows_by_resource[name] = 0

    load_info: Dict[str, Any] = {
        "project_external_key": getattr(project, "external_key", None),
        "rows_loaded_by_resource": rows_by_resource,
        "last_synced_at": now_iso,
    }

    return load_info
