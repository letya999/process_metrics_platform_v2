import logging
from uuid import uuid4

import services.dlt_jira_loader.flows.jira_sync as jira_sync_mod
import services.dlt_jira_loader.flows.project_sync as project_sync_mod
from services.dlt_jira_loader.flows.jira_sync import jira_sync_flow
from services.dlt_jira_loader.models.config import JiraSyncConfig


def test_jira_sync_flow_creates_and_finalizes_run():
    # prepare in-memory db_conn with one project
    project_id = uuid4()
    store = {
        "projects": [
            {
                "project_id": str(project_id),
                "external_id": "100",
                "external_key": "PROJ",
                "name": "Test Project",
                "credentials": {},
            }
        ]
    }

    cfg = JiraSyncConfig(project_uuids=[project_id], dataset_name="raw_jira_cloud_dlt")

    # Avoid Prefect server/client checks: stub get_run_logger in flow modules
    # Call the Prefect-decorated flow directly;
    # Prefect 3 will provide context when running
    # but for unit tests we simply call the wrapped function to execute pure logic.
    jira_sync_mod.get_run_logger = lambda *a, **k: logging.getLogger("test")
    project_sync_mod.get_run_logger = lambda *a, **k: logging.getLogger("test")
    res = jira_sync_flow.__wrapped__(db_conn=store, config=cfg)

    assert res["status"] in ("completed", "partial_failure")
    # pipeline run should be finalized in the in-memory store
    assert "pipeline_runs" in store
    assert len(store["pipeline_runs"]) == 1
