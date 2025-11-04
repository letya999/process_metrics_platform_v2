from dlt_jira_loader.app.flows.tasks.validation import validate_load


def test_validate_load_empty_rows():
    res = validate_load.fn({"rows_loaded_by_resource": {}})
    assert res["status"] == "ok"
    assert "total rows loaded is zero" in res["warnings"]


def test_validate_load_none_rows():
    res = validate_load.fn({})
    assert res["status"] == "ok"
    assert "no resources present in load_info" in res["warnings"]
