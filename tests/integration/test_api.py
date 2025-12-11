"""Integration tests for FastAPI endpoints.

These tests use mocked database sessions to verify API behavior
without requiring an actual database connection.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models.orm import (
    Project,
    ProjectAccess,
    ToolIntegration,
)


class TestIntegrationsAPI:
    """Tests for integrations API endpoints."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock async database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.delete = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        return session

    @pytest.fixture
    def client(self, mock_session):
        """Create test client with mocked DB."""

        async def override_get_db():
            yield mock_session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)
        yield client
        app.dependency_overrides.clear()

    @pytest.fixture
    def sample_integration(self):
        """Create a sample integration mock."""
        integration = MagicMock(spec=ToolIntegration)
        integration.id = uuid.UUID("12345678-1234-1234-1234-123456789012")
        integration.user_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        integration.integration_type_id = uuid.UUID(
            "22222222-2222-2222-2222-222222222222"
        )
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

    def test_list_integrations_empty(self, client, mock_session):
        """Test listing integrations when none exist."""
        # Mock empty result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        response = client.get("/api/v1/integrations")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []

    def test_list_integrations_with_data(
        self, client, mock_session, sample_integration
    ):
        """Test listing integrations with data."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_integration]
        mock_session.execute.return_value = mock_result

        response = client.get("/api/v1/integrations")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 1
        assert data[0]["instance_url"] == "https://example.atlassian.net"

    def test_get_integration_not_found(self, client, mock_session):
        """Test getting non-existent integration."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        integration_id = str(uuid.uuid4())
        response = client.get(f"/api/v1/integrations/{integration_id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_integration_success(self, client, mock_session, sample_integration):
        """Test getting an existing integration."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_integration
        mock_session.execute.return_value = mock_result

        response = client.get(f"/api/v1/integrations/{sample_integration.id}")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["instance_url"] == "https://example.atlassian.net"

    def test_delete_integration_not_found(self, client, mock_session):
        """Test deleting non-existent integration."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        integration_id = str(uuid.uuid4())
        response = client.delete(f"/api/v1/integrations/{integration_id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_integration_success(self, client, mock_session, sample_integration):
        """Test successfully deleting an integration."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_integration
        mock_session.execute.return_value = mock_result

        response = client.delete(f"/api/v1/integrations/{sample_integration.id}")

        assert response.status_code == status.HTTP_204_NO_CONTENT
        mock_session.delete.assert_called_once()


class TestProjectsAPI:
    """Tests for projects API endpoints."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock async database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.delete = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        return session

    @pytest.fixture
    def client(self, mock_session):
        """Create test client with mocked DB."""

        async def override_get_db():
            yield mock_session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)
        yield client
        app.dependency_overrides.clear()

    @pytest.fixture
    def sample_project(self):
        """Create a sample project mock."""
        project = MagicMock(spec=Project)
        project.id = uuid.UUID("33333333-3333-3333-3333-333333333333")
        project.owner_user_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        project.tool_integration_id = uuid.UUID("12345678-1234-1234-1234-123456789012")
        project.external_key = "PROJ"
        project.external_id = "10001"
        project.name = "Test Project"
        project.external_url = "https://example.atlassian.net/browse/PROJ"
        project.is_active = True
        project.created_at = datetime.now(timezone.utc)
        project.updated_at = datetime.now(timezone.utc)
        return project

    def test_list_projects_empty(self, client, mock_session):
        """Test listing projects when none exist."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        response = client.get("/api/v1/projects")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []

    def test_list_projects_with_data(self, client, mock_session, sample_project):
        """Test listing projects with data."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_project]
        mock_session.execute.return_value = mock_result

        response = client.get("/api/v1/projects")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 1
        assert data[0]["external_key"] == "PROJ"
        assert data[0]["name"] == "Test Project"

    def test_get_project_not_found(self, client, mock_session):
        """Test getting non-existent project."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        project_id = str(uuid.uuid4())
        response = client.get(f"/api/v1/projects/{project_id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_project_success(self, client, mock_session, sample_project):
        """Test getting an existing project."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_project
        mock_session.execute.return_value = mock_result

        response = client.get(f"/api/v1/projects/{sample_project.id}")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["external_key"] == "PROJ"

    def test_delete_project_not_found(self, client, mock_session):
        """Test deleting non-existent project."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        project_id = str(uuid.uuid4())
        response = client.delete(f"/api/v1/projects/{project_id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_project_success(self, client, mock_session, sample_project):
        """Test successfully deleting a project."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_project
        mock_session.execute.return_value = mock_result

        response = client.delete(f"/api/v1/projects/{sample_project.id}")

        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_list_projects_filter_by_user(self, client, mock_session, sample_project):
        """Test listing projects filtered by user ID."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_project]
        mock_session.execute.return_value = mock_result

        user_id = str(sample_project.owner_user_id)
        response = client.get(f"/api/v1/projects?user_id={user_id}")

        assert response.status_code == status.HTTP_200_OK


class TestMetricsAPI:
    """Tests for metrics API endpoints."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock async database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        return session

    @pytest.fixture
    def client(self, mock_session):
        """Create test client with mocked DB."""

        async def override_get_db():
            yield mock_session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)
        yield client
        app.dependency_overrides.clear()

    def test_get_lead_time_returns_empty_on_missing_view(self, client, mock_session):
        """Test getting lead time metrics when view doesn't exist."""
        # Simulate view not existing
        mock_session.execute.side_effect = Exception("relation does not exist")

        project_id = str(uuid.uuid4())
        response = client.get(f"/api/v1/metrics/lead-time?project_id={project_id}")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["items"] == []
        assert data["total_count"] == 0

    def test_get_velocity_returns_empty_on_missing_view(self, client, mock_session):
        """Test getting velocity metrics when view doesn't exist."""
        # Simulate view not existing
        mock_session.execute.side_effect = Exception("relation does not exist")

        project_id = str(uuid.uuid4())
        response = client.get(f"/api/v1/metrics/velocity?project_id={project_id}")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["items"] == []
        assert data["total_count"] == 0

    def test_get_throughput_returns_empty_on_missing_view(self, client, mock_session):
        """Test getting throughput metrics when view doesn't exist."""
        # Simulate view not existing
        mock_session.execute.side_effect = Exception("relation does not exist")

        project_id = str(uuid.uuid4())
        response = client.get(f"/api/v1/metrics/throughput?project_id={project_id}")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["items"] == []
        assert data["total_count"] == 0

    def test_refresh_metrics_success(self, client, mock_session):
        """Test refreshing metrics views."""
        mock_session.execute.return_value = None

        response = client.post("/api/v1/metrics/refresh")

        assert response.status_code == status.HTTP_202_ACCEPTED
        data = response.json()
        assert data["status"] == "success"

    def test_refresh_metrics_view_not_found(self, client, mock_session):
        """Test refreshing metrics when views don't exist."""
        mock_session.execute.side_effect = Exception("function does not exist")

        response = client.post("/api/v1/metrics/refresh")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_metrics_config(self, client, mock_session):
        """Test getting metrics configuration."""
        response = client.get("/api/v1/metrics/config")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "commitment_statuses" in data
        assert "done_statuses" in data


class TestProjectAccessAPI:
    """Tests for project access API endpoints."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock async database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.delete = AsyncMock()
        session.add = MagicMock()
        return session

    @pytest.fixture
    def client(self, mock_session):
        """Create test client with mocked DB."""

        async def override_get_db():
            yield mock_session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)
        yield client
        app.dependency_overrides.clear()

    @pytest.fixture
    def sample_project(self):
        """Create a sample project mock."""
        project = MagicMock(spec=Project)
        project.id = uuid.UUID("33333333-3333-3333-3333-333333333333")
        project.owner_user_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        return project

    @pytest.fixture
    def sample_access(self, sample_project):
        """Create a sample project access mock."""
        access = MagicMock(spec=ProjectAccess)
        access.id = uuid.UUID("44444444-4444-4444-4444-444444444444")
        access.project_id = sample_project.id
        access.user_id = uuid.UUID("55555555-5555-5555-5555-555555555555")
        access.access_level = "viewer"
        access.granted_by = sample_project.owner_user_id
        access.created_at = datetime.now(timezone.utc)
        return access

    def test_list_project_access_not_found_project(self, client, mock_session):
        """Test listing access for non-existent project."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        project_id = str(uuid.uuid4())
        response = client.get(f"/api/v1/projects/{project_id}/access")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_list_project_access_success(
        self, client, mock_session, sample_project, sample_access
    ):
        """Test listing access for existing project."""
        # First call returns project, second call returns access list
        mock_project_result = MagicMock()
        mock_project_result.scalar_one_or_none.return_value = sample_project

        mock_access_result = MagicMock()
        mock_access_result.scalars.return_value.all.return_value = [sample_access]

        mock_session.execute.side_effect = [mock_project_result, mock_access_result]

        response = client.get(f"/api/v1/projects/{sample_project.id}/access")

        assert response.status_code == status.HTTP_200_OK

    def test_revoke_owner_access_denied(self, client, mock_session, sample_project):
        """Test that revoking owner access is denied."""
        mock_project_result = MagicMock()
        mock_project_result.scalar_one_or_none.return_value = sample_project

        owner_access = MagicMock(spec=ProjectAccess)
        owner_access.access_level = "owner"

        mock_access_result = MagicMock()
        mock_access_result.scalar_one_or_none.return_value = owner_access

        mock_session.execute.side_effect = [mock_access_result]

        user_id = str(sample_project.owner_user_id)
        response = client.delete(
            f"/api/v1/projects/{sample_project.id}/access/{user_id}"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "owner access" in response.json()["detail"].lower()


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_health_check(self):
        """Test health check endpoint."""
        with TestClient(app) as client:
            response = client.get("/health")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["status"] == "healthy"

    def test_root_redirect(self):
        """Test root endpoint redirects to docs."""
        with TestClient(app, follow_redirects=False) as client:
            response = client.get("/")

            # Should redirect to /docs
            assert response.status_code in [
                status.HTTP_307_TEMPORARY_REDIRECT,
                status.HTTP_200_OK,
            ]
