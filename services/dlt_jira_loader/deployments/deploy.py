"""Register Prefect deployments for Jira sync flows (Phase 5, Task 17).

This script is minimal and focuses on local registrations. It avoids external
SaaS and relies on environment configuration for Prefect API.
"""
from __future__ import annotations

import os
from typing import Optional

try:
    from prefect import flow
    from prefect.deployments import Deployment
    from prefect.server.schemas.schedules import CronSchedule
except Exception:  # pragma: no cover - allow import in environments without prefect
    flow = None  # type: ignore
    Deployment = None  # type: ignore
    CronSchedule = None  # type: ignore

from services.dlt_jira_loader.flows.jira_sync import jira_sync_flow


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name)
    return v if v is not None else default


def main() -> None:
    if Deployment is None:
        print("Prefect is not available; skip deployment registration.")
        return

    environment = _env("ENV", "development")

    # Manual deployment (no schedule)
    manual = Deployment.build_from_flow(
        flow=jira_sync_flow,
        name=f"jira-sync-manual-{environment}",
        parameters={},
        work_queue_name=_env("PREFECT_WORK_QUEUE", "default"),
        tags=["jira", environment],
    )

    # Daily schedule at 02:00 UTC (can be adjusted later or replaced by wrapper)
    scheduled = Deployment.build_from_flow(
        flow=jira_sync_flow,
        name=f"jira-sync-daily-{environment}",
        parameters={},
        schedule=CronSchedule(cron="0 2 * * *", timezone="UTC"),
        work_queue_name=_env("PREFECT_WORK_QUEUE", "default"),
        tags=["jira", environment, "scheduled"],
    )

    manual.apply()
    scheduled.apply()

    print("Deployments registered:")
    print(f" - {manual.name}")
    print(f" - {scheduled.name}")


if __name__ == "__main__":
    main()
