"""Unit tests for app.api.projects business branches."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import projects as projects_api  # noqa: E402
from app.schemas.project import ProjectCreate, ProjectUpdate  # noqa: E402

_ADMIN = object()


def _make_db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    db.add = MagicMock()
    return db


def _scalar_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _scalars_result(values):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = values
    result.scalars.return_value = scalars
    return result


@pytest.mark.asyncio
async def test_list_projects_returns_scalars():
    db = _make_db()
    db.execute.return_value = _scalars_result([SimpleNamespace(id=uuid4())])

    result = await projects_api.list_projects(
        db=db, _admin=_ADMIN, user_id=None, integration_id=None, is_active=True
    )

    assert len(result) == 1
    db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_create_project_user_not_found():
    db = _make_db()
    db.execute = AsyncMock(side_effect=[_scalar_result(None)])

    with pytest.raises(HTTPException) as exc:
        await projects_api.create_project(
            db=db,
            project_data=ProjectCreate(
                tool_integration_id=uuid4(),
                external_key="ADS",
                external_id="100",
                name="Ads",
            ),
            user_id=uuid4(),
            _admin=_ADMIN,
        )

    assert exc.value.status_code == 404
    assert "User" in exc.value.detail


@pytest.mark.asyncio
async def test_create_project_integration_not_found():
    db = _make_db()
    db.execute = AsyncMock(side_effect=[_scalar_result(object()), _scalar_result(None)])

    with pytest.raises(HTTPException) as exc:
        await projects_api.create_project(
            db=db,
            project_data=ProjectCreate(
                tool_integration_id=uuid4(),
                external_key="ADS",
                external_id="100",
                name="Ads",
            ),
            user_id=uuid4(),
            _admin=_ADMIN,
        )

    assert exc.value.status_code == 404
    assert "Integration" in exc.value.detail


@pytest.mark.asyncio
async def test_create_project_duplicate_external_id_conflict():
    db = _make_db()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result(object()),
            _scalar_result(object()),
            _scalar_result(object()),
        ]
    )

    with pytest.raises(HTTPException) as exc:
        await projects_api.create_project(
            db=db,
            project_data=ProjectCreate(
                tool_integration_id=uuid4(),
                external_key="ADS",
                external_id="100",
                name="Ads",
            ),
            user_id=uuid4(),
            _admin=_ADMIN,
        )

    assert exc.value.status_code == 409
    assert "already exists" in exc.value.detail


@pytest.mark.asyncio
async def test_create_project_success():
    user_id = uuid4()
    integration_id = uuid4()
    db = _make_db()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result(object()),
            _scalar_result(object()),
            _scalar_result(None),
        ]
    )

    async def _refresh(project):
        project.id = uuid4()
        project.created_at = datetime.now(timezone.utc)
        project.updated_at = datetime.now(timezone.utc)
        project.is_active = True

    db.refresh.side_effect = _refresh

    result = await projects_api.create_project(
        db=db,
        project_data=ProjectCreate(
            tool_integration_id=integration_id,
            external_key="ADS",
            external_id="100",
            name="Ads",
            external_url="https://example.local/ads",
        ),
        user_id=user_id,
        _admin=_ADMIN,
    )

    assert result.owner_user_id == user_id
    assert result.tool_integration_id == integration_id
    assert result.external_key == "ADS"
    db.add.assert_called_once()
    db.commit.assert_called_once()
    db.refresh.assert_called_once()


@pytest.mark.asyncio
async def test_update_project_not_found():
    db = _make_db()
    db.execute.return_value = _scalar_result(None)

    with pytest.raises(HTTPException) as exc:
        await projects_api.update_project(
            db=db,
            project_id=uuid4(),
            _admin=_ADMIN,
            update_data=ProjectUpdate(name="New"),
        )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_update_project_updates_selected_fields():
    project = SimpleNamespace(
        id=uuid4(),
        name="Old",
        external_url="https://old",
        is_active=True,
    )
    db = _make_db()
    db.execute.return_value = _scalar_result(project)

    result = await projects_api.update_project(
        db=db,
        project_id=project.id,
        _admin=_ADMIN,
        update_data=ProjectUpdate(
            name="New", external_url="https://new", is_active=False
        ),
    )

    assert result.name == "New"
    assert result.external_url == "https://new"
    assert result.is_active is False
    db.flush.assert_called_once()
    db.refresh.assert_called_once_with(project)


@pytest.mark.asyncio
async def test_delete_project_not_found():
    db = _make_db()
    db.execute.return_value = _scalar_result(None)

    with pytest.raises(HTTPException) as exc:
        await projects_api.delete_project(db=db, project_id=uuid4(), _admin=_ADMIN)

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_project_success():
    project = SimpleNamespace(id=uuid4())
    db = _make_db()
    db.execute.return_value = _scalar_result(project)

    result = await projects_api.delete_project(
        db=db,
        project_id=project.id,
        _admin=_ADMIN,
    )

    assert result is None
    db.delete.assert_called_once_with(project)
