"""Main Jira sync flow with async DB."""
# ruff: noqa: E501
from __future__ import annotations

# Bootstrap path so this module can be executed as a script by Prefect. The
# lightweight helper lives next to other flows so it can be imported with a
# simple relative import regardless of execution context.
try:  # Keep flows runnable when Prefect copies only entrypoint
    pass  # type: ignore
except Exception:
    pass

from typing import Optional
from uuid import UUID as _PLACEHOLDER_UUID

from prefect import flow, get_run_logger

from ..infra.db import get_db_session
from ..infra.repositories.pipeline_run import create_pipeline_run, finalize_pipeline_run
from ..models.schemas.config import PipelineRunStatus


@flow(name="jira_sync_flow", log_prints=True)
async def jira_sync_flow(
    project_uuids: Optional[list[str]] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> dict:
    """Main Jira sync flow.

    Args:
        project_uuids: Projects to sync
        date_from: Start date (ISO)
        date_to: End date (ISO)

    Returns:
        Sync summary with metrics
    """
    logger = get_run_logger()

    # Normalize incoming project IDs: accept list of strings or UUID objects
    if project_uuids is not None:
        try:
            from uuid import UUID as _UUID

            project_uuids = [
                _UUID(p) if isinstance(p, str) else p for p in project_uuids
            ]
        except Exception:
            logger.error(
                "Invalid project_uuids provided; must be list of UUID strings or UUID objects"
            )
            raise

    # Create pipeline run
    async with get_db_session() as session:
        run_id = await create_pipeline_run(
            session=session,
            pipeline_id=_PLACEHOLDER_UUID(
                "00000000-0000-0000-0000-000000000000"
            ),  # placeholder
            run_type="scheduled",
            config={"project_uuids": project_uuids, "date_from": date_from},
        )

    logger.info(f"Started pipeline run: {run_id}")

    try:
        # TODO: Implement sync logic with async tasks
        total_rows = 0

        # Finalize success
        async with get_db_session() as session:
            await finalize_pipeline_run(
                session=session,
                run_id=run_id,
                status=PipelineRunStatus.SUCCESS.value,
                metrics={"total_rows": total_rows},
            )

        return {"status": "success", "total_rows": total_rows}

    except Exception as e:
        logger.error(f"Flow failed: {e}")

        async with get_db_session() as session:
            await finalize_pipeline_run(
                session=session,
                run_id=run_id,
                status=PipelineRunStatus.FAILED.value,
                error_message=str(e),
            )

        raise
