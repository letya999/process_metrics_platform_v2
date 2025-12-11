"""Tests for projects API endpoints."""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app


class TestListProjects:
    """Tests for GET /api/v1/projects."""

    def test_list_projects_empty(self, mock_db_session):
        """Test listing projects when none exist."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        response = client.get("/api/v1/projects")

        assert response.status_code == 200
        assert response.json() == []
        app.dependency_overrides.clear()

    def test_list_projects_with_data(self, mock_db_session, sample_project):
        """Test listing projects with data."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_project]
        mock_db_session.execute.return_value = mock_result

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        response = client.get("/api/v1/projects")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Test Project"
        assert data[0]["external_key"] == "PROJ"
        app.dependency_overrides.clear()

    def test_list_projects_filter_by_user(
        self, mock_db_session, sample_project, sample_user_id
    ):
        """Test listing projects filtered by user ID."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_project]
        mock_db_session.execute.return_value = mock_result

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        response = client.get(f"/api/v1/projects?user_id={sample_user_id}")

        assert response.status_code == 200
        app.dependency_overrides.clear()

    def test_list_projects_filter_by_active(self, mock_db_session, sample_project):
        """Test listing projects filtered by active status."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_project]
        mock_db_session.execute.return_value = mock_result

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        response = client.get("/api/v1/projects?is_active=true")

        assert response.status_code == 200
        app.dependency_overrides.clear()


class TestGetProject:
    """Tests for GET /api/v1/projects/{project_id}."""

    def test_get_project_success(self, mock_db_session, sample_project):
        """Test getting a project by ID."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_project
        mock_db_session.execute.return_value = mock_result

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        response = client.get(f"/api/v1/projects/{sample_project.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_project.id)
        assert data["name"] == "Test Project"
        app.dependency_overrides.clear()

    def test_get_project_not_found(self, mock_db_session, sample_project_id):
        """Test getting a non-existent project."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        response = client.get(f"/api/v1/projects/{sample_project_id}")

        assert response.status_code == 404
        app.dependency_overrides.clear()


class TestUpdateProject:
    """Tests for PUT /api/v1/projects/{project_id}."""

    def test_update_project_success(self, mock_db_session, sample_project):
        """Test updating a project."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_project
        mock_db_session.execute.return_value = mock_result

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        response = client.put(
            f"/api/v1/projects/{sample_project.id}",
            json={"name": "Updated Project Name"},
        )

        assert response.status_code == 200
        app.dependency_overrides.clear()

    def test_update_project_not_found(self, mock_db_session, sample_project_id):
        """Test updating a non-existent project."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        response = client.put(
            f"/api/v1/projects/{sample_project_id}",
            json={"name": "Updated Project Name"},
        )

        assert response.status_code == 404
        app.dependency_overrides.clear()


class TestDeleteProject:
    """Tests for DELETE /api/v1/projects/{project_id}."""

    def test_delete_project_success(self, mock_db_session, sample_project):
        """Test deleting a project."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_project
        mock_db_session.execute.return_value = mock_result

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        response = client.delete(f"/api/v1/projects/{sample_project.id}")

        assert response.status_code == 204
        mock_db_session.delete.assert_called_once()
        app.dependency_overrides.clear()

    def test_delete_project_not_found(self, mock_db_session, sample_project_id):
        """Test deleting a non-existent project."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        response = client.delete(f"/api/v1/projects/{sample_project_id}")

        assert response.status_code == 404
        app.dependency_overrides.clear()


class TestCreateProject:
    """Tests for POST /api/v1/projects."""

    def test_create_project_user_not_found(
        self, mock_db_session, sample_user_id, sample_integration_id
    ):
        """Test creating a project when user doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        response = client.post(
            f"/api/v1/projects?user_id={sample_user_id}",
            json={
                "tool_integration_id": str(sample_integration_id),
                "external_key": "PROJ",
                "external_id": "10001",
                "name": "Test Project",
            },
        )

        assert response.status_code == 404
        assert "User" in response.json()["detail"]
        app.dependency_overrides.clear()
