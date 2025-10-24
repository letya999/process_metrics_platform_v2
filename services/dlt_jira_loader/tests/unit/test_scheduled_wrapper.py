from __future__ import annotations

from uuid import uuid4

from services.dlt_jira_loader.flows.scheduled import jira_sync_scheduled_wrapper


def _make_proj(key: str, last_synced: dict | None = None, is_active: bool = True):
    return {
        "project_id": uuid4(),
        "external_id": key,
        "external_key": key,
        "is_active": is_active,
        "credentials": last_synced or {},
    }


def test_wrapper_no_projects():
    res = jira_sync_scheduled_wrapper.fn(None)
    assert res["status"].startswith("no_projects")


def test_wrapper_batches_and_filtering(monkeypatch):
    # create 7 projects, one inactive
    projects = [_make_proj(str(i)) for i in range(7)]
    projects.append(_make_proj("inactive", is_active=False))

    db_conn = {"projects": projects}

    # stub out the actual jira_sync_flow to avoid Prefect runtime during unit test
    monkeypatch.setattr(
        "services.dlt_jira_loader.flows.scheduled.jira_sync_flow",
        lambda db_conn, config: {"status": "started"},
    )

    # run with batch_size 3 -> 3 batches (3,3,1)
    res = jira_sync_scheduled_wrapper.fn(db_conn, batch_size=3)
    assert res["project_count"] == 7
    assert res["batches_started"] == 3
