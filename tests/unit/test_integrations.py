"""Tests for integrations API endpoints."""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app


class TestListIntegrationTypes:
    """Tests for GET /api/v1/integration-types."""

    def test_list_integration_types_empty(self, mock_db_session):
        """Test listing integration types when none exist."""
        # Mock empty result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        response = client.get("/api/v1/integration-types")

        assert response.status_code == 200
        assert response.json() == []
        app.dependency_overrides.clear()

    def test_list_integration_types_with_data(
        self, mock_db_session, sample_integration_type
    ):
        """Test listing integration types with data."""
        # Mock result with integration types
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_integration_type]
        mock_db_session.execute.return_value = mock_result

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        response = client.get("/api/v1/integration-types")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "jira_cloud"
        app.dependency_overrides.clear()


class TestListIntegrations:
    """Tests for GET /api/v1/integrations."""

    def test_list_integrations_empty(self, mock_db_session):
        """Test listing integrations when none exist."""
        # Mock empty result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        response = client.get("/api/v1/integrations")

        assert response.status_code == 200
        assert response.json() == []
        app.dependency_overrides.clear()

    def test_list_integrations_with_data(self, mock_db_session, sample_integration):
        """Test listing integrations with data."""
        # Mock result with integrations
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_integration]
        mock_db_session.execute.return_value = mock_result

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        response = client.get("/api/v1/integrations")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["instance_url"] == "https://example.atlassian.net"
        app.dependency_overrides.clear()

    def test_list_integrations_filter_by_user(
        self, mock_db_session, sample_integration, sample_user_id
    ):
        """Test listing integrations filtered by user ID."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_integration]
        mock_db_session.execute.return_value = mock_result

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        response = client.get(f"/api/v1/integrations?user_id={sample_user_id}")

        assert response.status_code == 200
        app.dependency_overrides.clear()


class TestGetIntegration:
    """Tests for GET /api/v1/integrations/{integration_id}."""

    def test_get_integration_success(self, mock_db_session, sample_integration):
        """Test getting an integration by ID."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_integration
        mock_db_session.execute.return_value = mock_result

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        response = client.get(f"/api/v1/integrations/{sample_integration.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_integration.id)
        app.dependency_overrides.clear()

    def test_get_integration_not_found(self, mock_db_session, sample_integration_id):
        """Test getting a non-existent integration."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        response = client.get(f"/api/v1/integrations/{sample_integration_id}")

        assert response.status_code == 404
        app.dependency_overrides.clear()


class TestCreateIntegration:
    """Tests for POST /api/v1/integrations."""

    def test_create_integration_user_not_found(
        self, mock_db_session, sample_user_id, sample_integration_type_id
    ):
        """Test creating an integration when user doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        response = client.post(
            f"/api/v1/integrations?user_id={sample_user_id}",
            json={
                "integration_type_id": str(sample_integration_type_id),
                "instance_url": "https://example.atlassian.net",
                "user_email": "test@example.com",
                "api_token": "test_token",
            },
        )

        assert response.status_code == 404
        assert "User" in response.json()["detail"]
        app.dependency_overrides.clear()


class TestDeleteIntegration:
    """Tests for DELETE /api/v1/integrations/{integration_id}."""

    def test_delete_integration_success(self, mock_db_session, sample_integration):
        """Test deleting an integration."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_integration
        mock_db_session.execute.return_value = mock_result

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        response = client.delete(f"/api/v1/integrations/{sample_integration.id}")

        assert response.status_code == 204
        mock_db_session.delete.assert_called_once()
        app.dependency_overrides.clear()

    def test_delete_integration_not_found(self, mock_db_session, sample_integration_id):
        """Test deleting a non-existent integration."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        response = client.delete(f"/api/v1/integrations/{sample_integration_id}")

        assert response.status_code == 404
        app.dependency_overrides.clear()
