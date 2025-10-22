"""Register Prefect deployments for Jira sync flows.

Adds resilience: wait for Prefect API, build + apply deployments, then upsert
Prefect identifiers into `platform.pipelines` (name = 'jira_sync').
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Optional, Tuple

try:
    from prefect import flow
    from prefect.deployments import Deployment
    from prefect.server.schemas.schedules import CronSchedule
except Exception:  # pragma: no cover - allow import in environments without prefect
    flow = None  # type: ignore
    Deployment = None  # type: ignore
    CronSchedule = None  # type: ignore

from services.dlt_jira_loader.flows.jira_sync import jira_sync_flow
from services.dlt_jira_loader.utils.db import upsert_pipeline_prefect_ids


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name)
    return v if v is not None else default


def wait_for_prefect(api_url: str, timeout_seconds: int = 120, backoff_seconds: int = 2) -> None:
    """Poll Prefect API health until available or timeout.

    Uses requests lazily to avoid importing if not installed in tests.
    """
    import requests

    health = api_url.rstrip("/") + "/health"
    deadline = time.time() + timeout_seconds
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        try:
            r = requests.get(health, timeout=5)
            if r.ok:
                return
        except Exception:
            pass
        time.sleep(backoff_seconds)
    raise RuntimeError(f"Prefect API not ready at {health}")


async def _get_ids_with_client(flow_name: str, deployment_name: str) -> Tuple[Optional[str], Optional[str]]:
    """Best-effort read of flow_id and deployment_id using Prefect client.

    Returns (flow_id, deployment_id) as strings or (None, None) if unavailable.
    """
    try:
        # Prefect 2 style client
        from prefect.client.orchestration import get_client  # type: ignore

        async with get_client() as client:  # type: ignore
            # name format: "{flow_name}/{deployment_name}"
            name = f"{flow_name}/{deployment_name}"
            dep = await client.read_deployment_by_name(name)  # type: ignore
            if dep is None:
                return None, None
            deployment_id = str(getattr(dep, "id", None) or getattr(dep, "deployment_id", None) or "") or None
            flow_id = str(getattr(dep, "flow_id", None) or "") or None
            return flow_id, deployment_id
    except Exception:
        return None, None


def main() -> None:
    if Deployment is None:
        print("Prefect is not available; skip deployment registration.")
        return

    api_url = _env("PREFECT_API_URL", "http://prefect-server:4200/api")
    work_pool = _env("PREFECT_WORK_POOL", "default")
    work_queue = _env("PREFECT_WORK_QUEUE", "default")
    environment = _env("ENV", "development")

    # Wait for Prefect API to be ready
    try:
        if api_url:
            wait_for_prefect(str(api_url))
    except Exception as exc:
        print(f"Warning: Prefect API wait failed: {exc}")

    # Manual deployment (no schedule)
    manual = Deployment.build_from_flow(
        flow=jira_sync_flow,
        name=f"jira-sync-manual-{environment}",
        parameters={},
        work_queue_name=work_queue,  # Prefect 2 workers
        tags=["jira", environment],
    )

    # Daily schedule at 02:00 UTC (can be adjusted later or replaced by wrapper)
    scheduled = Deployment.build_from_flow(
        flow=jira_sync_flow,
        name=f"jira-sync-daily-{environment}",
        parameters={},
        schedule=CronSchedule(cron="0 2 * * *", timezone="UTC"),
        work_queue_name=work_queue,
        tags=["jira", environment, "scheduled"],
    )

    manual.apply()
    scheduled.apply()

    print("Deployments registered:")
    print(f" - {manual.name}")
    print(f" - {scheduled.name}")

    # Best-effort: resolve IDs and upsert into platform.pipelines
    try:
        flow_name = getattr(jira_sync_flow, "name", None) or "jira_sync_flow"
        # Prefect uses flow function name for the flow; deployment name is set above
        m_flow_id, m_dep_id = asyncio.run(_get_ids_with_client(flow_name, manual.name))
        s_flow_id, s_dep_id = asyncio.run(_get_ids_with_client(flow_name, scheduled.name))

        # Prefer scheduled deployment id if available; otherwise manual
        deployment_id = s_dep_id or m_dep_id
        flow_id = s_flow_id or m_flow_id

        if deployment_id or flow_id:
            upsert_pipeline_prefect_ids(
                pipeline_name="jira_sync",
                prefect_flow_id=flow_id,
                prefect_deployment_id=deployment_id,
            )
            print("Updated platform.pipelines with Prefect IDs")
        else:
            print("Could not resolve Prefect IDs; DB upsert skipped")
    except Exception as exc:  # pragma: no cover - best-effort only
        print(f"Warning: failed to upsert Prefect IDs to DB: {exc}")


if __name__ == "__main__":
    main()
