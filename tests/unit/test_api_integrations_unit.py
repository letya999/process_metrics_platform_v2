"""Unit tests for app.api.integrations business branches."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import integrations as integrations_api  # noqa: E402
from app.schemas.integration import IntegrationCreate, IntegrationUpdate  # noqa: E402


def _scalar_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    # Ensure it's not an AsyncMock to avoid unwanted coroutines
    result.scalar_one_or_none.__name__ = "scalar_one_or_none"
    return result


def _scalars_result(values):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = values
    result.scalars.return_value = scalars
    # Ensure it's not an AsyncMock
    result.scalars.__name__ = "scalars"
    scalars.all.__name__ = "all"
    return result


def _make_db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    db.add = MagicMock()
    return db


def _integration_obj(**kwargs):
    now = datetime.now(timezone.utc)
    defaults = {
        "id": uuid4(),
        "user_id": uuid4(),
        "integration_type_id": uuid4(),
        "integration_type": None,
        "instance_url": "https://jira.local",
        "user_email": "user@example.com",
        "is_active": True,
        "secret_provider": "hardcoded",
        "api_token_unsafe": None,
        "secret_reference": None,
        "last_sync_at": None,
        "last_sync_status": None,
        "last_error": None,
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


@pytest.mark.asyncio
async def test_list_integrations_maps_type_name():
    jira_type = SimpleNamespace(name="jira_cloud")
    integration = _integration_obj(integration_type=jira_type)
    db = _make_db()
    db.execute.return_value = _scalars_result([integration])

    result = await integrations_api.list_integrations(
        db=db, _admin=MagicMock(), user_id=None, is_active=True
    )

    assert len(result) == 1
    assert result[0].integration_type_name == "jira_cloud"


@pytest.mark.asyncio
async def test_create_integration_user_not_found():
    db = _make_db()
    db.execute = AsyncMock(side_effect=[_scalar_result(None)])

    with pytest.raises(HTTPException) as exc:
        await integrations_api.create_integration(
            db=db,
            _admin=MagicMock(),
            integration_data=IntegrationCreate(
                integration_type_id=uuid4(),
                instance_url="https://jira.local",
                user_email="u@example.com",
                api_token="secret",
                secret_provider="hardcoded",
            ),
            user_id=uuid4(),
        )

    assert exc.value.status_code == 404
    assert "User" in exc.value.detail


@pytest.mark.asyncio
async def test_create_integration_type_not_found():
    db = _make_db()
    db.execute = AsyncMock(side_effect=[_scalar_result(object()), _scalar_result(None)])

    with pytest.raises(HTTPException) as exc:
        await integrations_api.create_integration(
            db=db,
            _admin=MagicMock(),
            integration_data=IntegrationCreate(
                integration_type_id=uuid4(),
                instance_url="https://jira.local",
                user_email="u@example.com",
                api_token="secret",
                secret_provider="hardcoded",
            ),
            user_id=uuid4(),
        )

    assert exc.value.status_code == 404
    assert "Integration type" in exc.value.detail


@pytest.mark.asyncio
async def test_create_integration_success_hardcoded_token():
    integration_type_id = uuid4()
    user_id = uuid4()
    integration_type = SimpleNamespace(name="jira_cloud")
    db = _make_db()
    db.execute = AsyncMock(
        side_effect=[_scalar_result(object()), _scalar_result(integration_type)]
    )

    async def _refresh(integration):
        now = datetime.now(timezone.utc)
        integration.id = uuid4()
        integration.user_id = user_id
        integration.integration_type_id = integration_type_id
        integration.is_active = True
        integration.created_at = now
        integration.updated_at = now
        integration.last_sync_at = None
        integration.last_sync_status = None
        integration.last_error = None

    db.refresh.side_effect = _refresh

    result = await integrations_api.create_integration(
        db=db,
        _admin=MagicMock(),
        integration_data=IntegrationCreate(
            integration_type_id=integration_type_id,
            instance_url="https://jira.local",
            user_email="u@example.com",
            api_token="super-secret",
            secret_provider="hardcoded",
        ),
        user_id=user_id,
    )

    assert result.integration_type_name == "jira_cloud"
    assert result.user_id == user_id
    db.add.assert_called_once()
    db.flush.assert_called_once()
    db.refresh.assert_called_once()


@pytest.mark.asyncio
async def test_create_integration_success_secret_reference():
    integration_type_id = uuid4()
    user_id = uuid4()
    integration_type = SimpleNamespace(name="gitlab")
    db = _make_db()
    db.execute = AsyncMock(
        side_effect=[_scalar_result(object()), _scalar_result(integration_type)]
    )

    async def _refresh(integration):
        now = datetime.now(timezone.utc)
        integration.id = uuid4()
        integration.user_id = user_id
        integration.integration_type_id = integration_type_id
        integration.is_active = True
        integration.created_at = now
        integration.updated_at = now
        integration.last_sync_at = None
        integration.last_sync_status = None
        integration.last_error = None

    db.refresh.side_effect = _refresh

    result = await integrations_api.create_integration(
        db=db,
        _admin=MagicMock(),
        integration_data=IntegrationCreate(
            integration_type_id=integration_type_id,
            instance_url="https://gitlab.local",
            user_email="u@example.com",
            api_token="unused",
            secret_provider="vault",
        ),
        user_id=user_id,
    )

    assert result.integration_type_name == "gitlab"
    created_obj = db.add.call_args.args[0]
    assert created_obj.api_token_unsafe is None
    assert created_obj.secret_reference.startswith("INTEGRATION_TOKEN_")


@pytest.mark.asyncio
async def test_trigger_sync_inactive_integration():
    db = _make_db()
    integration = _integration_obj(is_active=False)
    db.execute.return_value = _scalar_result(integration)

    with pytest.raises(HTTPException) as exc:
        await integrations_api.trigger_sync(
            db=db, integration_id=integration.id, _admin=MagicMock()
        )

    assert exc.value.status_code == 400
    assert "not active" in exc.value.detail


@pytest.mark.asyncio
async def test_trigger_sync_success_for_jira(monkeypatch):
    integration = _integration_obj(
        integration_type=SimpleNamespace(name="jira_cloud"),
        is_active=True,
    )
    db = _make_db()
    db.execute.return_value = _scalar_result(integration)

    class _Client:
        async def trigger_job(self, job_name, run_config):
            assert job_name == "jira_sync_job"
            assert run_config["resources"]["integration"]["config"][
                "integration_id"
            ] == str(integration.id)
            return {
                "data": {
                    "launchRun": {
                        "__typename": "LaunchRunSuccess",
                        "run": {"runId": "r1", "status": "STARTED"},
                    }
                }
            }

    monkeypatch.setattr(integrations_api, "DagsterClient", lambda: _Client())

    result = await integrations_api.trigger_sync(
        db=db, integration_id=integration.id, _admin=MagicMock()
    )

    assert result.run_id == "r1"
    assert result.status == "STARTED"
    assert integration.last_sync_status == "running"
    db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_trigger_sync_returns_500_for_launch_error(monkeypatch):
    integration = _integration_obj(
        integration_type=SimpleNamespace(name="gitlab"),
        is_active=True,
    )
    db = _make_db()
    db.execute.return_value = _scalar_result(integration)

    class _Client:
        async def trigger_job(self, *_args, **_kwargs):
            return {
                "data": {"launchRun": {"__typename": "PythonError", "message": "boom"}}
            }

    monkeypatch.setattr(integrations_api, "DagsterClient", lambda: _Client())

    with pytest.raises(HTTPException) as exc:
        await integrations_api.trigger_sync(
            db=db, integration_id=integration.id, _admin=MagicMock()
        )

    assert exc.value.status_code == 500
    assert "Failed to trigger sync" in exc.value.detail


@pytest.mark.asyncio
async def test_get_sync_status_success(monkeypatch):
    integration = _integration_obj()
    db = _make_db()
    db.execute.return_value = _scalar_result(integration)

    class _Client:
        async def get_run_status(self, run_id):
            assert run_id == "run-1"
            return {
                "data": {
                    "runOrError": {
                        "__typename": "Run",
                        "runId": "run-1",
                        "status": "SUCCESS",
                        "startTime": None,
                        "endTime": None,
                    }
                }
            }

    monkeypatch.setattr(integrations_api, "DagsterClient", lambda: _Client())

    result = await integrations_api.get_sync_status(
        db=db, integration_id=integration.id, run_id="run-1", _admin=MagicMock()
    )

    assert result.run_id == "run-1"
    assert result.status == "SUCCESS"


@pytest.mark.asyncio
async def test_get_sync_status_run_not_found(monkeypatch):
    integration = _integration_obj()
    db = _make_db()
    db.execute.return_value = _scalar_result(integration)

    class _Client:
        async def get_run_status(self, _run_id):
            return {"data": {"runOrError": {"__typename": "RunNotFoundError"}}}

    monkeypatch.setattr(integrations_api, "DagsterClient", lambda: _Client())

    with pytest.raises(HTTPException) as exc:
        await integrations_api.get_sync_status(
            db=db, integration_id=integration.id, run_id="missing", _admin=MagicMock()
        )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_sync_status_unexpected_error_type(monkeypatch):
    integration = _integration_obj()
    db = _make_db()
    db.execute.return_value = _scalar_result(integration)

    class _Client:
        async def get_run_status(self, _run_id):
            return {
                "data": {"runOrError": {"__typename": "PythonError", "message": "bad"}}
            }

    monkeypatch.setattr(integrations_api, "DagsterClient", lambda: _Client())

    with pytest.raises(HTTPException) as exc:
        await integrations_api.get_sync_status(
            db=db, integration_id=integration.id, run_id="run-1", _admin=MagicMock()
        )

    assert exc.value.status_code == 500
    assert "Failed to get run status" in exc.value.detail


@pytest.mark.asyncio
async def test_update_integration_updates_token_for_hardcoded_provider():
    integration = _integration_obj(secret_provider="hardcoded")
    db = _make_db()
    db.execute.return_value = _scalar_result(integration)

    result = await integrations_api.update_integration(
        db=db,
        integration_id=integration.id,
        _admin=MagicMock(),
        update_data=IntegrationUpdate(api_token="new-secret", is_active=False),
    )

    assert result.is_active is False
    assert integration.api_token_unsafe == "new-secret"
    db.flush.assert_called_once()
    db.refresh.assert_called_once_with(integration)


# ── list_jira_projects ────────────────────────────────────────────────────────


def _make_httpx_response(status_code: int, json_data: dict):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = str(json_data)
    return resp


@pytest.mark.asyncio
async def test_list_jira_projects_not_found():
    db = _make_db()
    db.execute.return_value = _scalar_result(None)

    with pytest.raises(HTTPException) as exc:
        await integrations_api.list_jira_projects(
            db=db, integration_id=uuid4(), _admin=MagicMock()
        )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_list_jira_projects_no_token_raises_422():
    integration = _integration_obj(
        api_token_unsafe=None,
        secret_reference=None,
        secret_provider=None,
    )
    db = _make_db()
    db.execute.return_value = _scalar_result(integration)

    with pytest.raises(HTTPException) as exc:
        await integrations_api.list_jira_projects(
            db=db, integration_id=uuid4(), _admin=MagicMock()
        )

    assert exc.value.status_code == 422
    assert "token" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_list_jira_projects_no_instance_url_raises_422():
    integration = _integration_obj(api_token_unsafe="tok", instance_url=None)
    db = _make_db()
    db.execute.return_value = _scalar_result(integration)

    with pytest.raises(HTTPException) as exc:
        await integrations_api.list_jira_projects(
            db=db, integration_id=uuid4(), _admin=MagicMock()
        )

    assert exc.value.status_code == 422
    assert "instance_url" in exc.value.detail


@pytest.mark.asyncio
async def test_list_jira_projects_jira_api_error_raises_502():
    from unittest.mock import patch

    integration = _integration_obj(
        api_token_unsafe="tok", instance_url="https://jira.local"
    )
    db = _make_db()
    db.execute.return_value = _scalar_result(integration)

    bad_resp = MagicMock()
    bad_resp.status_code = 401
    bad_resp.text = "Unauthorized"

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=bad_resp)

    with patch("app.api.integrations.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(HTTPException) as exc:
            await integrations_api.list_jira_projects(
                db=db, integration_id=uuid4(), _admin=MagicMock()
            )

    assert exc.value.status_code == 502


@pytest.mark.asyncio
async def test_list_jira_projects_returns_projects_with_already_imported_flag(
    monkeypatch,
):
    from unittest.mock import patch
    from uuid import uuid4 as _uuid4

    int_id = _uuid4()
    integration = _integration_obj(
        id=int_id,
        api_token_unsafe="tok",
        instance_url="https://jira.local",
    )

    jira_page = {
        "values": [
            {
                "key": "ADS",
                "id": "10001",
                "name": "Ads Project",
                "self": "https://jira.local/rest/api/3/project/10001",
            },
            {"key": "MKT", "id": "10002", "name": "Marketing", "self": None},
        ],
        "isLast": True,
    }

    jira_resp = MagicMock()
    jira_resp.status_code = 200
    jira_resp.json.return_value = jira_page

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=jira_resp)

    # Simulate ADS (id=10001) already imported
    imported_rows = MagicMock()
    imported_rows.fetchall.return_value = [("10001",)]

    db = _make_db()
    # 1st execute: integration lookup, 2nd: imported project IDs
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result(integration),
            imported_rows,
        ]
    )

    with patch("app.api.integrations.httpx.AsyncClient", return_value=mock_client):
        result = await integrations_api.list_jira_projects(
            db=db, integration_id=int_id, _admin=MagicMock()
        )

    assert len(result) == 2
    ads = next(r for r in result if r.key == "ADS")
    mkt = next(r for r in result if r.key == "MKT")
    assert ads.already_imported is True
    assert mkt.already_imported is False
