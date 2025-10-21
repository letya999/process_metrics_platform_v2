from types import SimpleNamespace

from services.dlt_jira_loader.flows.tasks.checkpoint import upsert_checkpoint
from services.dlt_jira_loader.flows.tasks.load import run_load


def test_run_load_simulation_returns_loadinfo(monkeypatch):
    # create fake project and resources mapping
    project = SimpleNamespace(external_key="PROJ")
    resources = {"issues": lambda: iter([])}

    # ensure simulation mode (DLT_ENABLE_REAL_RUN not set)
    monkeypatch.delenv("DLT_ENABLE_REAL_RUN", raising=False)

    load_info = run_load.fn(project, resources)

    assert "rows_loaded_by_resource" in load_info
    assert "last_synced_at" in load_info


def test_upsert_checkpoint_in_memory_store():
    # in-memory db_conn
    db_conn = {}
    project = {"tool_integration_id": "ti-1", "project_id": "p-1"}
    load_info = {
        "last_synced_at": "2025-10-20T12:00:00Z",
        "rows_loaded_by_resource": {"issues": 10},
    }

    cp = upsert_checkpoint.fn(db_conn, project, load_info, entity_type="issues")

    assert isinstance(cp, dict)
    assert db_conn.get("checkpoints") is not None
    assert db_conn["checkpoints"][0]["tool_integration_id"] == "ti-1"
