from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request

from app.api import admin as admin_api
from app.schemas.admin import (
    AdminLoginRequest,
    CalculationSettingUpsert,
    CommitmentRuleUpsert,
    SliceRuleUpsert,
    UnitBindingUpsert,
)
from app.services.admin_auth import AdminSession


def _make_db():
    db = MagicMock()
    db.execute = AsyncMock()
    return db


def _make_request():
    scope = {
        "type": "http",
        "client": ("127.0.0.1", 123),
        "path": "/api/v1/admin/auth/login",
    }
    return Request(scope)


def _mappings_result(*, first=None, all_rows=None):
    result = MagicMock()
    mappings = MagicMock()
    mappings.first.return_value = first
    mappings.all.return_value = all_rows if all_rows is not None else []
    result.mappings.return_value = mappings
    return result


def _scalars_result(values):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = values
    result.scalars.return_value = scalars
    return result


def _scalar_result(value):
    result = MagicMock()
    result.scalar.return_value = value
    return result


@pytest.mark.asyncio
async def test_get_current_admin_missing_token(monkeypatch):
    monkeypatch.setattr(admin_api, "parse_bearer_token", lambda _h: None)
    with pytest.raises(HTTPException) as exc:
        await admin_api._get_current_admin(None)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_admin_invalid_or_non_admin(monkeypatch):
    monkeypatch.setattr(admin_api, "parse_bearer_token", lambda _h: "tok")
    monkeypatch.setattr(
        admin_api,
        "get_session",
        lambda _t: AdminSession(
            user_id="u",
            email="e@x",
            display_name="d",
            is_admin=False,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        ),
    )
    with pytest.raises(HTTPException) as exc:
        await admin_api._get_current_admin("Bearer tok")
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_admin_success(monkeypatch):
    session = AdminSession(
        user_id=str(uuid4()),
        email="e@x",
        display_name="d",
        is_admin=True,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    monkeypatch.setattr(admin_api, "parse_bearer_token", lambda _h: "tok")
    monkeypatch.setattr(admin_api, "get_session", lambda _t: session)
    assert await admin_api._get_current_admin("Bearer tok") == session


@pytest.mark.asyncio
async def test_admin_login_invalid_and_success(monkeypatch):
    db = _make_db()
    db.execute.return_value = _mappings_result(first=None)
    request = _make_request()

    with pytest.raises(HTTPException):
        await admin_api.admin_login(
            request, AdminLoginRequest(email="a@x", password="x"), db
        )

    user_id = uuid4()
    row = {
        "id": user_id,
        "email": "admin@example.com",
        "display_name": "Admin",
        "password_hash": "secret",
        "is_admin": True,
        "is_active": True,
    }
    db.execute.return_value = _mappings_result(first=row)
    # verify_password now returns (is_valid, needs_rehash)
    monkeypatch.setattr(admin_api, "verify_password", lambda *_args: (True, False))
    expires_at = datetime.now(UTC) + timedelta(hours=1)
    monkeypatch.setattr(
        admin_api, "create_access_token", lambda *_args: ("tok", expires_at)
    )
    save_session = MagicMock()
    monkeypatch.setattr(admin_api, "save_session", save_session)

    res = await admin_api.admin_login(
        request, AdminLoginRequest(email="admin@example.com", password="secret"), db
    )
    assert res.access_token == "tok"
    assert res.user_id == user_id
    save_session.assert_called_once()


@pytest.mark.asyncio
async def test_admin_login_lazy_rehash(monkeypatch):
    db = _make_db()
    user_id = uuid4()
    row = {
        "id": user_id,
        "email": "admin@example.com",
        "display_name": "Admin",
        "password_hash": "plaintext_secret",
        "is_admin": True,
        "is_active": True,
    }
    db.execute.return_value = _mappings_result(first=row)
    # Simulate legacy plaintext password requiring rehash
    monkeypatch.setattr(admin_api, "verify_password", lambda *_args: (True, True))
    monkeypatch.setattr(admin_api, "hash_password", lambda p: "hashed_" + p)

    expires_at = datetime.now(UTC) + timedelta(hours=1)
    monkeypatch.setattr(
        admin_api, "create_access_token", lambda *_args: ("tok", expires_at)
    )
    monkeypatch.setattr(admin_api, "save_session", MagicMock())

    request = _make_request()
    await admin_api.admin_login(
        request, AdminLoginRequest(email="admin@example.com", password="secret"), db
    )

    # Check that update was called
    # 1st call: select user
    # 2nd call: update password
    assert db.execute.call_count == 2
    update_sql = db.execute.call_args_list[1][0][0]
    update_params = db.execute.call_args_list[1][0][1]
    assert "UPDATE platform.users SET password_hash" in str(update_sql)
    assert update_params["h"] == "hashed_secret"


@pytest.mark.asyncio
async def test_admin_login_invalid_password(monkeypatch):
    db = _make_db()
    db.execute.return_value = _mappings_result(
        first={
            "id": uuid4(),
            "email": "admin@example.com",
            "display_name": "Admin",
            "password_hash": "stored",
            "is_admin": True,
            "is_active": True,
        }
    )
    monkeypatch.setattr(admin_api, "verify_password", lambda *_args: (False, False))
    request = _make_request()
    with pytest.raises(HTTPException) as exc:
        await admin_api.admin_login(
            request, AdminLoginRequest(email="admin@example.com", password="bad"), db
        )
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_admin_me_and_logout(monkeypatch):
    session = AdminSession(
        user_id=str(uuid4()),
        email="admin@example.com",
        display_name="Admin",
        is_admin=True,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    me = await admin_api.admin_me(session)
    assert me.email == "admin@example.com"

    revoke = MagicMock()
    monkeypatch.setattr(admin_api, "parse_bearer_token", lambda _h: "tok")
    monkeypatch.setattr(admin_api, "revoke_token", revoke)
    assert (await admin_api.admin_logout("Bearer tok"))["status"] == "ok"
    revoke.assert_called_once_with("tok")


@pytest.mark.asyncio
async def test_catalog_endpoints_map_rows():
    db = _make_db()
    pid, bid, sid, fid, iid, cid = uuid4(), uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    db.execute = AsyncMock(
        side_effect=[
            _mappings_result(
                all_rows=[
                    {"project_id": pid, "project_key": "PRJ", "project_name": "Project"}
                ]
            ),
            _mappings_result(
                all_rows=[{"board_id": bid, "board_name": "Board", "project_id": pid}]
            ),
            _mappings_result(
                all_rows=[
                    {
                        "column_id": cid,
                        "board_id": bid,
                        "column_name": "In Progress",
                        "position": 1,
                        "status_id": sid,
                        "status_name": "In Progress",
                        "status_category": "indeterminate",
                    }
                ]
            ),
            _mappings_result(
                all_rows=[
                    {
                        "status_id": sid,
                        "project_id": pid,
                        "status_name": "Done",
                        "category": "done",
                    }
                ]
            ),
            _mappings_result(
                all_rows=[
                    {
                        "field_key_id": fid,
                        "project_id": pid,
                        "external_key": "custom_1",
                        "name": "SP",
                    }
                ]
            ),
            _mappings_result(
                all_rows=[
                    {
                        "issue_type_id": iid,
                        "project_id": pid,
                        "issue_type_name": "Story",
                    }
                ]
            ),
        ]
    )
    admin = AdminSession(
        str(uuid4()), "a@x", "A", True, datetime.now(UTC) + timedelta(hours=1)
    )
    assert (await admin_api.catalog_projects(db, admin))[0].project_key == "PRJ"
    assert (await admin_api.catalog_boards(db, admin, pid))[0].board_id == bid
    assert (await admin_api.catalog_board_columns(db, admin, bid))[0].column_id == cid
    assert (await admin_api.catalog_statuses(db, admin, pid))[0].status_id == sid
    assert (await admin_api.catalog_field_keys(db, admin, pid))[0].field_key_id == fid
    assert (await admin_api.catalog_issue_types(db, admin, pid))[0].issue_type_id == iid


@pytest.mark.asyncio
async def test_catalog_schema_map_and_contract_catalog():
    db = _make_db()
    db.execute = AsyncMock(
        side_effect=[
            _mappings_result(
                all_rows=[
                    {
                        "table_name": "projects",
                        "column_name": "id",
                        "data_type": "uuid",
                    },
                    {
                        "table_name": "projects",
                        "column_name": "name",
                        "data_type": "text",
                    },
                ]
            ),
            _mappings_result(
                all_rows=[
                    {
                        "from_table": "issues",
                        "from_column": "project_id",
                        "to_table": "projects",
                        "to_column": "id",
                    }
                ]
            ),
            _mappings_result(
                all_rows=[
                    {
                        "metric_code": "m1",
                        "calc_code": "flow_active_days",
                        "unit_code": "story_points",
                        "uses_commitment_points": True,
                    },
                    {
                        "metric_code": "m2",
                        "calc_code": "custom",
                        "unit_code": "days",
                        "uses_commitment_points": False,
                    },
                ]
            ),
        ]
    )
    admin = AdminSession(
        str(uuid4()), "a@x", "A", True, datetime.now(UTC) + timedelta(hours=1)
    )
    schema = await admin_api.catalog_clean_jira_schema_map(db, admin)
    assert schema.tables[0].table_name == "projects"
    assert schema.relations[0].from_table == "issues"

    contracts = await admin_api.contract_catalog(db, admin)
    assert contracts[0].requires_unit_binding == "required"
    assert contracts[0].requires_commitment == "required"
    assert contracts[1].requires_unit_binding == "none"


@pytest.mark.asyncio
async def test_commitment_rules_list_upsert_delete_and_errors():
    db = _make_db()
    admin = AdminSession(
        str(uuid4()), "a@x", "A", True, datetime.now(UTC) + timedelta(hours=1)
    )
    rid = uuid4()
    payload = CommitmentRuleUpsert(
        project_id=uuid4(),
        board_id=uuid4(),
        calc_code="lead_time_days",
        start_column_id=uuid4(),
        end_column_id=uuid4(),
    )
    list_row = {
        "id": rid,
        "project_id": None,
        "board_id": None,
        "calc_code": "lead_time_days",
        "target_calculation_name": "lead_time_days",
        "start_column_id": payload.start_column_id,
        "end_column_id": payload.end_column_id,
        "start_column_name_snapshot": "Start",
        "end_column_name_snapshot": "End",
    }
    calc = {"id": uuid4(), "calc_code": "lead_time_days"}
    cols = [
        {"id": payload.start_column_id, "name": "Start"},
        {"id": payload.end_column_id, "name": "End"},
    ]

    # Mock for successful delete
    mock_delete_result = MagicMock()
    mock_delete_result.rowcount = 1

    # Mock for 404 delete
    mock_delete_404 = MagicMock()
    mock_delete_404.rowcount = 0

    db.execute = AsyncMock(
        side_effect=[
            _mappings_result(all_rows=[list_row]),
            _mappings_result(first=calc),
            _mappings_result(all_rows=cols),
            _mappings_result(first=list_row),
            mock_delete_result,  # delete_commitment_rule success
            mock_delete_404,  # delete_commitment_rule 404
            _mappings_result(first=None),  # upsert 404
            _mappings_result(first=calc),
            _mappings_result(all_rows=cols),
            IntegrityError("stmt", "params", Exception("dup")),
        ]
    )
    listed = await admin_api.list_commitment_rules(db, admin, None, None, None)
    created = await admin_api.upsert_commitment_rule(payload, db, admin)
    deleted = await admin_api.delete_commitment_rule(rid, db, admin)
    assert listed[0].id == rid
    assert created.calc_code == "lead_time_days"
    assert deleted["status"] == "ok"

    # Test DELETE 404
    with pytest.raises(HTTPException) as exc_del:
        await admin_api.delete_commitment_rule(uuid4(), db, admin)
    assert exc_del.value.status_code == 404

    with pytest.raises(HTTPException) as not_found:
        await admin_api.upsert_commitment_rule(
            CommitmentRuleUpsert(
                id=uuid4(),
                project_id=payload.project_id,
                board_id=payload.board_id,
                calc_code="lead_time_days",
                start_column_id=payload.start_column_id,
                end_column_id=payload.end_column_id,
            ),
            db,
            admin,
        )
    assert not_found.value.status_code == 404

    with pytest.raises(HTTPException) as conflict:
        await admin_api.upsert_commitment_rule(payload, db, admin)
    assert conflict.value.status_code == 409
    assert "Conflict" in str(conflict.value.detail)


@pytest.mark.asyncio
async def test_calculation_settings_list_upsert_delete_and_errors():
    db = _make_db()
    admin = AdminSession(
        str(uuid4()), "a@x", "A", True, datetime.now(UTC) + timedelta(hours=1)
    )
    sid, pid = uuid4(), uuid4()
    list_row = {
        "id": sid,
        "project_id": pid,
        "calc_code": "ttm_days",
        "metric_code": "time_to_market",
        "settings_type": "issue_type_filter",
        "settings_json": {"include": ["Epic"]},
        "enabled": True,
    }
    payload = CalculationSettingUpsert(
        project_id=pid,
        calc_code="ttm_days",
        settings_type="issue_type_filter",
        settings_json={"include": ["Epic"]},
        enabled=True,
    )
    calc = {"id": uuid4(), "calc_code": "ttm_days", "metric_code": "time_to_market"}

    mock_delete_result = MagicMock()
    mock_delete_result.rowcount = 1

    db.execute = AsyncMock(
        side_effect=[
            _mappings_result(all_rows=[list_row]),
            _mappings_result(first=calc),
            _mappings_result(first=list_row),
            mock_delete_result,
            _mappings_result(first=None),
            _mappings_result(first=calc),
            IntegrityError("stmt", "params", Exception("dup")),
        ]
    )
    listed = await admin_api.list_calculation_settings(db, admin, pid, "ttm_days", None)
    upserted = await admin_api.upsert_calculation_setting(payload, db, admin)
    deleted = await admin_api.delete_calculation_setting(sid, db, admin)
    assert listed[0].id == sid
    assert upserted.metric_code == "time_to_market"
    assert deleted["status"] == "ok"

    with pytest.raises(HTTPException) as not_found:
        await admin_api.upsert_calculation_setting(
            CalculationSettingUpsert(
                calc_code="ttm_days",
                settings_type="issue_type_filter",
                settings_json={},
                enabled=True,
            ),
            db,
            admin,
        )
    assert not_found.value.status_code == 404

    with pytest.raises(HTTPException) as conflict:
        await admin_api.upsert_calculation_setting(payload, db, admin)
    assert conflict.value.status_code == 409


@pytest.mark.asyncio
async def test_units_list_upsert_and_conflict():
    db = _make_db()
    admin = AdminSession(
        str(uuid4()), "a@x", "A", True, datetime.now(UTC) + timedelta(hours=1)
    )
    uid, pid = uuid4(), uuid4()
    row = {
        "id": uid,
        "project_id": pid,
        "unit_code": "story_points",
        "display_symbol": "SP",
        "source_field_id": None,
        "source_entity": "clean_jira.field_keys",
    }
    db.execute = AsyncMock(
        side_effect=[
            _mappings_result(all_rows=[row]),
            _mappings_result(first={"id": uid}),
            _mappings_result(first=row),
            _mappings_result(first=None),
            _mappings_result(first=row),
            _mappings_result(first=None),
            IntegrityError("stmt", "params", Exception("dup")),
        ]
    )
    listed = await admin_api.list_units(db, admin, pid)
    updated = await admin_api.upsert_unit(
        "story_points",
        UnitBindingUpsert(
            project_id=pid, display_symbol="SP", source_entity="clean_jira.field_keys"
        ),
        db,
        admin,
    )
    created = await admin_api.upsert_unit(
        "story_points",
        UnitBindingUpsert(
            project_id=pid, display_symbol="SP", source_entity="clean_jira.field_keys"
        ),
        db,
        admin,
    )
    assert listed[0].id == uid
    assert updated.unit_code == "story_points"
    assert created.unit_code == "story_points"

    with pytest.raises(HTTPException) as exc:
        await admin_api.upsert_unit(
            "story_points",
            UnitBindingUpsert(
                display_symbol="SP", source_entity="clean_jira.field_keys"
            ),
            db,
            admin,
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_delete_unit_success_and_404():
    db = _make_db()
    admin = AdminSession(
        str(uuid4()), "a@x", "A", True, datetime.now(UTC) + timedelta(hours=1)
    )
    uid = uuid4()

    mock_ok = MagicMock()
    mock_ok.rowcount = 1
    mock_404 = MagicMock()
    mock_404.rowcount = 0

    db.execute = AsyncMock(side_effect=[mock_ok, mock_404])

    result = await admin_api.delete_unit(uid, db, admin)
    assert result["status"] == "ok"

    with pytest.raises(HTTPException) as exc:
        await admin_api.delete_unit(uuid4(), db, admin)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_slice_rules_list_upsert_delete_and_errors():
    db = _make_db()
    admin = AdminSession(
        str(uuid4()), "a@x", "A", True, datetime.now(UTC) + timedelta(hours=1)
    )
    rid = uuid4()
    row = {
        "id": rid,
        "project_id": None,
        "rule_name": "By Type",
        "target_definition_id": None,
        "target_definition_name": None,
        "source_table": "clean_jira.issue_types",
        "group_by_source_column": "name",
        "enabled": True,
    }
    payload = SliceRuleUpsert(
        rule_name="By Type",
        source_table="clean_jira.issue_types",
        group_by_source_column="name",
        enabled=True,
    )

    mock_delete_result = MagicMock()
    mock_delete_result.rowcount = 1

    db.execute = AsyncMock(
        side_effect=[
            _mappings_result(all_rows=[row]),
            _mappings_result(first=row),
            mock_delete_result,
            _mappings_result(first=None),
            IntegrityError("stmt", "params", Exception("dup")),
        ]
    )
    listed = await admin_api.list_slice_rules(db, admin, None, None)
    created = await admin_api.upsert_slice_rule(payload, db, admin)
    deleted = await admin_api.delete_slice_rule(rid, db, admin)
    assert listed[0].id == rid
    assert created.rule_name == "By Type"
    assert deleted["status"] == "ok"

    with pytest.raises(HTTPException) as not_found:
        await admin_api.upsert_slice_rule(
            SliceRuleUpsert(
                id=uuid4(),
                rule_name="By Type",
                source_table="clean_jira.issue_types",
                group_by_source_column="name",
                enabled=True,
            ),
            db,
            admin,
        )
    assert not_found.value.status_code == 404

    with pytest.raises(HTTPException) as conflict:
        await admin_api.upsert_slice_rule(payload, db, admin)
    assert conflict.value.status_code == 409


@pytest.mark.asyncio
async def test_validate_config_with_and_without_issues(monkeypatch):
    db = _make_db()
    pid = uuid4()
    admin = AdminSession(
        str(uuid4()), "a@x", "A", True, datetime.now(UTC) + timedelta(hours=1)
    )
    monkeypatch.setattr(
        admin_api, "REQUIRED_SETTINGS_BY_CALC", {"ttm_days": ["issue_type_filter"]}
    )

    db.execute = AsyncMock(
        side_effect=[
            _mappings_result(all_rows=[{"project_id": pid, "project_key": "PRJ"}]),
            _scalars_result(["lead_time_days"]),
            _mappings_result(first=None),
            _scalar_result(0),
            _scalar_result(0),
            _mappings_result(all_rows=[{"project_id": pid, "project_key": "PRJ"}]),
            _scalars_result(["lead_time_days"]),
            _mappings_result(first={"source_field_id": uuid4()}),
            _scalar_result(1),
            _scalar_result(1),
        ]
    )

    issues_res = await admin_api.validate_config(db, admin, project_id=pid)
    codes = {issue.code for issue in issues_res.issues}
    assert {
        "missing_story_points_unit",
        "missing_commitment_rule",
        "missing_calc_setting",
    } <= codes

    ok_res = await admin_api.validate_config(db, admin, project_id=pid)
    assert ok_res.issues == []


@pytest.mark.asyncio
async def test_admin_jobs_list_and_launch():
    admin = AdminSession(
        str(uuid4()), "a@x", "A", True, datetime.now(UTC) + timedelta(hours=1)
    )
    jobs = await admin_api.list_admin_jobs(admin)
    assert any(j.job_name == "jira_sync_job" for j in jobs)

    class _Dagster:
        async def trigger_job(self, job_name, run_config=None):
            assert job_name == "jira_raw_job"
            assert run_config is None
            return {
                "data": {
                    "launchRun": {
                        "__typename": "LaunchRunSuccess",
                        "run": {"runId": "r-1", "status": "STARTED"},
                    }
                }
            }

    old = admin_api.DagsterClient
    admin_api.DagsterClient = lambda: _Dagster()
    try:
        out = await admin_api.launch_admin_job(
            admin_api.AdminJobLaunchRequest(job_name="jira_raw_job"),
            admin,
        )
    finally:
        admin_api.DagsterClient = old

    assert out.run_id == "r-1"
    assert out.status == "STARTED"


@pytest.mark.asyncio
async def test_admin_job_launch_rejects_unknown_job():
    admin = AdminSession(
        str(uuid4()), "a@x", "A", True, datetime.now(UTC) + timedelta(hours=1)
    )
    with pytest.raises(HTTPException) as exc:
        await admin_api.launch_admin_job(
            admin_api.AdminJobLaunchRequest(job_name="unknown_job"),
            admin,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_admin_job_run_details_success_and_not_found():
    admin = AdminSession(
        str(uuid4()), "a@x", "A", True, datetime.now(UTC) + timedelta(hours=1)
    )

    class _DagsterOk:
        async def get_run_details(self, run_id, event_limit=100):
            assert run_id == "run-1"
            assert event_limit == 100
            return {
                "data": {
                    "runOrError": {
                        "__typename": "Run",
                        "runId": "run-1",
                        "status": "FAILURE",
                        "startTime": 10.0,
                        "endTime": 20.0,
                        "stepStats": [
                            {"stepKey": "a", "status": "SUCCESS"},
                            {"stepKey": "b", "status": "FAILURE"},
                        ],
                        "eventConnection": {
                            "events": [
                                {
                                    "__typename": "MessageEvent",
                                    "timestamp": 12.0,
                                    "level": "ERROR",
                                    "eventType": "STEP_FAILURE",
                                    "message": "boom",
                                }
                            ]
                        },
                    }
                }
            }

    old = admin_api.DagsterClient
    admin_api.DagsterClient = lambda: _DagsterOk()
    try:
        out = await admin_api.get_admin_job_run_details("run-1", admin)
    finally:
        admin_api.DagsterClient = old

    assert out.status == "FAILURE"
    assert out.total_steps == 2
    assert out.completed_steps == 2
    assert out.failed_steps == 1
    assert out.progress_pct == 100.0
    assert len(out.errors) == 1

    class _DagsterMissing:
        async def get_run_details(self, *_args, **_kwargs):
            return {"data": {"runOrError": {"__typename": "RunNotFoundError"}}}

    admin_api.DagsterClient = lambda: _DagsterMissing()
    try:
        with pytest.raises(HTTPException) as exc:
            await admin_api.get_admin_job_run_details("missing", admin)
    finally:
        admin_api.DagsterClient = old
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_list_metric_recalc_jobs_returns_all():
    admin = AdminSession(
        str(uuid4()), "a@x", "A", True, datetime.now(UTC) + timedelta(hours=1)
    )
    jobs = await admin_api.list_metric_recalc_jobs(admin)
    job_names = {j.job_name for j in jobs}
    assert "recalculate_lead_time_job" in job_names
    assert "recalculate_velocity_job" in job_names
    assert "recalculate_sprint_health_job" in job_names
    assert "recalculate_aging_extended_job" in job_names
    # None of the pipeline jobs should be in the metric jobs list
    assert "jira_sync_job" not in job_names
    assert len(jobs) == len(admin_api.METRIC_RECALC_JOBS)


@pytest.mark.asyncio
async def test_launch_metric_batch_all_succeed():
    admin = AdminSession(
        str(uuid4()), "a@x", "A", True, datetime.now(UTC) + timedelta(hours=1)
    )

    class _Dagster:
        def __init__(self):
            self.calls = []

        async def trigger_job(self, job_name, run_config=None):
            self.calls.append(job_name)
            return {
                "data": {
                    "launchRun": {
                        "__typename": "LaunchRunSuccess",
                        "run": {"runId": f"run-{job_name}", "status": "STARTED"},
                    }
                }
            }

    fake = _Dagster()
    old = admin_api.DagsterClient
    admin_api.DagsterClient = lambda: fake
    try:
        result = await admin_api.launch_metric_batch(
            admin_api.AdminBatchJobLaunchRequest(
                job_names=["recalculate_lead_time_job", "recalculate_velocity_job"]
            ),
            admin,
        )
    finally:
        admin_api.DagsterClient = old

    assert len(result) == 2
    assert result[0].job_name == "recalculate_lead_time_job"
    assert result[0].run_id == "run-recalculate_lead_time_job"
    assert result[0].status == "STARTED"
    assert result[0].error is None
    assert result[1].job_name == "recalculate_velocity_job"
    assert result[1].error is None


@pytest.mark.asyncio
async def test_launch_metric_batch_partial_failure():
    admin = AdminSession(
        str(uuid4()), "a@x", "A", True, datetime.now(UTC) + timedelta(hours=1)
    )

    class _Dagster:
        async def trigger_job(self, job_name, run_config=None):
            if job_name == "recalculate_velocity_job":
                raise RuntimeError("Dagster connection refused")
            return {
                "data": {
                    "launchRun": {
                        "__typename": "LaunchRunSuccess",
                        "run": {"runId": "run-lt", "status": "STARTED"},
                    }
                }
            }

    old = admin_api.DagsterClient
    admin_api.DagsterClient = lambda: _Dagster()
    try:
        result = await admin_api.launch_metric_batch(
            admin_api.AdminBatchJobLaunchRequest(
                job_names=["recalculate_lead_time_job", "recalculate_velocity_job"]
            ),
            admin,
        )
    finally:
        admin_api.DagsterClient = old

    assert len(result) == 2
    lt = next(r for r in result if r.job_name == "recalculate_lead_time_job")
    vel = next(r for r in result if r.job_name == "recalculate_velocity_job")
    assert lt.run_id == "run-lt"
    assert lt.error is None
    assert vel.status == "LAUNCH_FAILED"
    assert "connection refused" in vel.error


@pytest.mark.asyncio
async def test_launch_metric_batch_dagster_launch_error_typename():
    admin = AdminSession(
        str(uuid4()), "a@x", "A", True, datetime.now(UTC) + timedelta(hours=1)
    )

    class _Dagster:
        async def trigger_job(self, job_name, run_config=None):
            return {
                "data": {
                    "launchRun": {
                        "__typename": "PythonError",
                        "message": "asset not found",
                    }
                }
            }

    old = admin_api.DagsterClient
    admin_api.DagsterClient = lambda: _Dagster()
    try:
        result = await admin_api.launch_metric_batch(
            admin_api.AdminBatchJobLaunchRequest(
                job_names=["recalculate_lead_time_job"]
            ),
            admin,
        )
    finally:
        admin_api.DagsterClient = old

    assert result[0].status == "LAUNCH_FAILED"
    assert "asset not found" in result[0].error


@pytest.mark.asyncio
async def test_launch_metric_batch_rejects_unknown_job():
    admin = AdminSession(
        str(uuid4()), "a@x", "A", True, datetime.now(UTC) + timedelta(hours=1)
    )
    with pytest.raises(HTTPException) as exc:
        await admin_api.launch_metric_batch(
            admin_api.AdminBatchJobLaunchRequest(
                job_names=["recalculate_lead_time_job", "unknown_job_xyz"]
            ),
            admin,
        )
    assert exc.value.status_code == 400
    assert "unknown_job_xyz" in exc.value.detail
