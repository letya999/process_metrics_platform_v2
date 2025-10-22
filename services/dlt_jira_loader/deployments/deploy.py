"""Register Prefect deployments for Jira sync flows (Phase 5, Task 17).

This script is minimal and focuses on local registrations. It avoids external
SaaS and relies on environment configuration for Prefect API.
"""
from __future__ import annotations

import os
import sys
import time
from typing import Any, Dict, Optional

try:
    from prefect.deployments import Deployment
    from prefect.server.schemas.schedules import CronSchedule
    from prefect.client.orchestration import get_client
    from prefect.server.schemas.actions import WorkPoolCreate
except Exception:  # pragma: no cover - allow import in environments without prefect
    Deployment = None  # type: ignore
    CronSchedule = None  # type: ignore
    get_client = None  # type: ignore
    WorkPoolCreate = None  # type: ignore

from services.dlt_jira_loader.flows.jira_sync import jira_sync_flow


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name)
    return v if v is not None else default


def wait_for_prefect(api_url: str, timeout_sec: int = 120, interval_sec: int = 3) -> None:
    """Wait for Prefect server to be ready using orchestration client."""
    if get_client is None:
        print("Prefect not installed; skipping wait_for_prefect")
        return
    deadline = time.time() + timeout_sec
    last_err: Optional[Exception] = None
    while time.time() < deadline:
        try:
            # Prefect 3 client uses context manager
            import asyncio

            async def _ping() -> None:
                async with get_client() as client:  # type: ignore
                    await client.read_healthcheck()

            asyncio.run(_ping())
            return
        except Exception as exc:  # pragma: no cover - timing dependent
            last_err = exc
            time.sleep(interval_sec)
    raise RuntimeError(f"Prefect API not ready at {api_url}: {last_err}")


def ensure_work_pool(name: str) -> None:
    """Create work pool if it does not exist."""
    if get_client is None:
        return
    import asyncio

    async def _run() -> None:
        async with get_client() as client:  # type: ignore
            try:
                await client.read_work_pool(name)
                return
            except Exception:
                pass
            body = WorkPoolCreate(name=name)
            await client.create_work_pool(body)

    try:
        asyncio.run(_run())
    except Exception:
        # non-fatal
        pass


def upsert_pipeline_ids(db_env: Dict[str, str], *, name: str, flow_id: str, deployment_id: str) -> None:
    """Best-effort upsert into platform.pipelines using asyncpg if available.

    Reads DB_* from environment. No secrets are printed; only lengths for debug.
    """
    try:
        import asyncio
        import asyncpg  # type: ignore

        async def _run() -> None:
            conn = await asyncpg.connect(
                host=db_env.get("DB_HOST", "postgres"),
                database=db_env.get("DB_NAME", "process_metrics_v2"),
                user=db_env.get("DB_USER", "postgres"),
                password=db_env.get("DB_PASSWORD", ""),
            )
            try:
                # create if not exists, update ids
                await conn.execute(
                    """
                    INSERT INTO platform.pipelines (name, prefect_flow_id, prefect_deployment_id)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (name)
                    DO UPDATE SET
                        prefect_flow_id = EXCLUDED.prefect_flow_id,
                        prefect_deployment_id = EXCLUDED.prefect_deployment_id,
                        updated_at = now()
                    """,
                    name,
                    flow_id,
                    deployment_id,
                )
            finally:
                await conn.close()

        asyncio.run(_run())
    except Exception as exc:
        # best-effort: log concise message and continue
        print(f"pipeline upsert skipped: {type(exc).__name__}: {exc}")


def main() -> None:
    if Deployment is None:
        print("Prefect is not available; skip deployment registration.")
        return

    environment = _env("ENV", "development")
    api_url = _env("PREFECT_API_URL", "http://prefect-server:4200/api") or ""
    wait_for_prefect(api_url)

    # Allow a separate pool for DLT-heavy jobs
    work_pool = _env("DLT_WORK_POOL", None) or _env("PREFECT_WORK_POOL", "default")
    ensure_work_pool(work_pool or "default")

    manual = Deployment.build_from_flow(
        flow=jira_sync_flow,
        name=f"jira-sync-manual-{environment}",
        parameters={},
        work_pool_name=work_pool,
        tags=["jira", environment],
    )

    scheduled = Deployment.build_from_flow(
        flow=jira_sync_flow,
        name=f"jira-sync-daily-{environment}",
        parameters={},
        schedule=CronSchedule(cron="0 2 * * *", timezone="UTC"),
        work_pool_name=work_pool,
        tags=["jira", environment, "scheduled"],
    )

    manual.apply()
    scheduled.apply()

    print("Deployments registered:")
    print(f" - {manual.name}")
    print(f" - {scheduled.name}")

    # Upsert into platform.pipelines
    # We record the daily scheduled deployment as the primary deployment
    try:
        deployment_id = getattr(scheduled, "id", None) or getattr(scheduled, "deployment_id", None)
        flow_id = getattr(scheduled, "flow_id", None) or ""
        if deployment_id and flow_id:
            db_env = {k: os.getenv(k, "") for k in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD")}
            upsert_pipeline_ids(db_env, name="jira_sync", flow_id=str(flow_id), deployment_id=str(deployment_id))
    except Exception as exc:
        print(f"failed to upsert pipelines: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
