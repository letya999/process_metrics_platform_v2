"""Async pipeline run repository for dlt_jira_loader."""
# ruff: noqa: E501
import json
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


async def create_pipeline_run(
    session: AsyncSession,
    pipeline_id: UUID,
    run_type: str,
    config: dict,
) -> UUID:
    """Create pipeline run and return id."""
    from uuid import UUID as _UUID

    from sqlalchemy import text

    # If caller passed zero-UUID as placeholder, try to resolve a real pipeline id.
    # This avoids foreign-key violations when flows run without a real pipeline record.
    zero_uuid = _UUID("00000000-0000-0000-0000-000000000000")
    if pipeline_id == zero_uuid:
        # Look up seeded pipeline (e.g. 'jira_sync')
        sel = text("SELECT id FROM platform.pipelines WHERE name = :name LIMIT 1")
        sel_res = await session.execute(sel, {"name": "jira_sync"})
        found = sel_res.scalar_one_or_none()
        if found:
            pipeline_id = found
        else:
            # Create a pipeline record to avoid FK errors and keep metadata
            ins = text(
                """
            INSERT INTO platform.pipelines (name, description, is_active, config)
            VALUES (:name, :description, true, :config)
            RETURNING id
            """
            )
            config_payload = json.dumps({"default_dataset": "raw_jira_cloud_dlt"})
            ins_res = await session.execute(
                ins,
                {
                    "name": "jira_sync",
                    "description": "Jira sync pipeline (auto-created)",
                    "config": config_payload,
                },
            )
            pipeline_id = ins_res.scalar_one()

    # Keep run_type in callers for compatibility, but store it inside the config JSON
    cfg = dict(config or {})
    if run_type:
        # don't overwrite existing explicit key
        cfg.setdefault("run_type", run_type)

    query = text(
        """
    INSERT INTO platform.pipeline_runs (pipeline_id, status, config, started_at)
    VALUES (:pipeline_id, 'running', :config, :started_at)
    RETURNING id
    """
    )

    result = await session.execute(
        query,
        {
            "pipeline_id": pipeline_id,
            "config": json.dumps(cfg),
            "started_at": datetime.now(timezone.utc),
        },
    )
    return result.scalar_one()


async def finalize_pipeline_run(
    session: AsyncSession,
    run_id: UUID,
    status: str,
    metrics: Optional[dict] = None,
    error_message: Optional[str] = None,
) -> None:
    """Finalize pipeline run."""
    from sqlalchemy import text

    query = text(
        """
    UPDATE platform.pipeline_runs
    SET status = :status, metrics = :metrics, error_message = :error_message, completed_at = :completed_at
    WHERE id = :run_id
    """
    )

    await session.execute(
        query,
        {
            "run_id": run_id,
            "status": status,
            "metrics": json.dumps(metrics or {}),
            "error_message": error_message,
            "completed_at": datetime.now(timezone.utc),
        },
    )
