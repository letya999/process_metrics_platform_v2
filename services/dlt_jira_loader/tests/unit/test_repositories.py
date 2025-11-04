"""Unit tests for repositories."""

import pytest
from dlt_jira_loader.app.infra.repositories.pipeline_run import create_pipeline_run


@pytest.mark.asyncio
async def test_create_pipeline_run(test_db, sample_project_id):
    """Test pipeline run creation."""
    run_id = await create_pipeline_run(
        session=test_db,
        pipeline_id=sample_project_id,
        run_type="manual",
        config={},
    )

    assert run_id is not None
