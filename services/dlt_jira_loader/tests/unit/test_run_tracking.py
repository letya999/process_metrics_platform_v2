from services.dlt_jira_loader.utils import db as db_utils


def test_ensure_pipeline_and_create_run():
    store = {}

    pid = db_utils.ensure_pipeline(store, "jira_sync")
    assert isinstance(pid, str)
    # calling again returns same pipeline id
    pid2 = db_utils.ensure_pipeline(store, "jira_sync")
    assert pid == pid2

    run_id = db_utils.create_pipeline_run(
        store, pipeline_name="jira_sync", config={"a": 1}
    )
    assert isinstance(run_id, str)
    assert "pipeline_runs" in store
    runs = store["pipeline_runs"]
    assert any(r["id"] == run_id and r["status"] == "running" for r in runs)


def test_finalize_pipeline_run_sets_status_and_metrics():
    store = {}
    # prepare run
    run_id = db_utils.create_pipeline_run(store, pipeline_name="jira_sync", config={})

    res = db_utils.finalize_pipeline_run(
        store, run_id, status="completed", metrics={"total_projects": 1, "failures": 0}
    )

    assert res["status"] == "completed"
    assert "completed_at" in res
    assert res.get("metrics", {}).get("total_projects") == 1
    # duration_seconds should be present (int) or absent if parsing failed
    assert "duration_seconds" in res and isinstance(res["duration_seconds"], int)
