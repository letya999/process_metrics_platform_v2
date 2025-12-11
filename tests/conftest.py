"""Shared pytest fixtures."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.main import app
from app.models.orm import (
    IntegrationTypeModel,
    Project,
    ToolIntegration,
    User,
)


@pytest.fixture
def sample_jira_issue():
    """Sample Jira issue data for testing."""
    return {
        "id": "10001",
        "key": "PROJ-1",
        "fields": {
            "summary": "Test issue",
            "status": {"name": "Done"},
            "issuetype": {"name": "Story"},
            "created": "2024-01-01T10:00:00.000+0000",
            "updated": "2024-01-02T10:00:00.000+0000",
        },
    }


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    return session


@pytest.fixture
def sample_user_id():
    """Sample user UUID for testing."""
    return uuid.UUID("12345678-1234-1234-1234-123456789012")


@pytest.fixture
def sample_integration_id():
    """Sample integration UUID for testing."""
    return uuid.UUID("23456789-2345-2345-2345-234567890123")


@pytest.fixture
def sample_integration_type_id():
    """Sample integration type UUID for testing."""
    return uuid.UUID("34567890-3456-3456-3456-345678901234")


@pytest.fixture
def sample_project_id():
    """Sample project UUID for testing."""
    return uuid.UUID("45678901-4567-4567-4567-456789012345")


@pytest.fixture
def sample_user(sample_user_id):
    """Create a sample User object for testing."""
    user = MagicMock(spec=User)
    user.id = sample_user_id
    user.email = "test@example.com"
    user.display_name = "Test User"
    user.password_hash = "hashed_password"
    user.is_active = True
    user.is_admin = False
    user.created_at = datetime.now(timezone.utc)
    user.updated_at = datetime.now(timezone.utc)
    return user


@pytest.fixture
def sample_integration_type(sample_integration_type_id):
    """Create a sample IntegrationTypeModel object for testing."""
    integration_type = MagicMock(spec=IntegrationTypeModel)
    integration_type.id = sample_integration_type_id
    integration_type.name = "jira_cloud"
    integration_type.description = "Jira Cloud integration"
    integration_type.is_active = True
    return integration_type


@pytest.fixture
def sample_integration(
    sample_integration_id, sample_user_id, sample_integration_type_id
):
    """Create a sample ToolIntegration object for testing."""
    integration = MagicMock(spec=ToolIntegration)
    integration.id = sample_integration_id
    integration.user_id = sample_user_id
    integration.integration_type_id = sample_integration_type_id
    integration.instance_url = "https://example.atlassian.net"
    integration.user_email = "test@example.com"
    integration.secret_provider = "hardcoded"
    integration.api_token_unsafe = "test_token"
    integration.is_active = True
    integration.last_sync_at = None
    integration.last_sync_status = None
    integration.last_error = None
    integration.created_at = datetime.now(timezone.utc)
    integration.updated_at = datetime.now(timezone.utc)

    # Mock integration_type relationship
    integration_type = MagicMock()
    integration_type.name = "jira_cloud"
    integration.integration_type = integration_type

    return integration


@pytest.fixture
def sample_project(sample_project_id, sample_user_id, sample_integration_id):
    """Create a sample Project object for testing."""
    project = MagicMock(spec=Project)
    project.id = sample_project_id
    project.owner_user_id = sample_user_id
    project.tool_integration_id = sample_integration_id
    project.external_key = "PROJ"
    project.external_id = "10001"
    project.name = "Test Project"
    project.external_url = "https://example.atlassian.net/browse/PROJ"
    project.is_active = True
    project.created_at = datetime.now(timezone.utc)
    project.updated_at = datetime.now(timezone.utc)
    return project


@pytest.fixture
def override_get_db(mock_db_session):
    """Override the get_db dependency with a mock."""

    async def _override_get_db():
        yield mock_db_session

    return _override_get_db


@pytest.fixture
def test_client(override_get_db):
    """Create a test client with mocked database."""
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def mock_dagster_client():
    """Create a mock DagsterClient."""
    with patch("app.api.integrations.DagsterClient") as mock:
        client_instance = AsyncMock()
        mock.return_value = client_instance
        yield client_instance
