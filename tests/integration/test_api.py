"""Integration tests for FastAPI endpoints with dependency overrides."""

from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import require_admin
from app.database import get_db
from app.main import app
from app.services.admin_auth import AdminSession

pytestmark = pytest.mark.integration


class _FakeResult:
    def __init__(self, *, scalars=None, scalar_value=None, mappings=None, one=None):
        self._scalars = scalars
        self._scalar = scalar_value
        self._mappings = mappings
        self._one = one

    def scalars(self):
        return SimpleNamespace(all=lambda: self._scalars or [])

    def scalar(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._one

    def mappings(self):
        rows = self._mappings or []
        first = rows[0] if rows else None
        return SimpleNamespace(all=lambda: rows, first=lambda: first)


class _FakeAsyncSession:
    def __init__(self):
        now = datetime(2026, 1, 10, tzinfo=timezone.utc)
        integration_type_id = uuid4()
        user_id = uuid4()
        integration_id = uuid4()
        project_id = uuid4()

        self.integration_type = SimpleNamespace(
            id=integration_type_id,
            name="jira_cloud",
            description="Jira Cloud integration",
            is_active=True,
        )
        self.integration = SimpleNamespace(
            id=integration_id,
            user_id=user_id,
            integration_type_id=integration_type_id,
            integration_type=self.integration_type,
            instance_url="https://jira.example.com",
            user_email="owner@example.com",
            is_active=True,
            last_sync_at=None,
            last_sync_status=None,
            last_error=None,
            created_at=now,
            updated_at=now,
        )
        self.project = SimpleNamespace(
            id=project_id,
            owner_user_id=user_id,
            tool_integration_id=integration_id,
            external_key="ADS",
            external_id="1001",
            name="Ads Platform",
            external_url="https://jira.example.com/projects/ADS",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        self.lead_time_row = {
            "issue_id": uuid4(),
            "issue_key": "ADS-42",
            "summary": "Ship endpoint hardening",
            "project_id": project_id,
            "project_key": "ADS",
            "project_name": "Ads Platform",
            "issue_type": "Story",
            "hierarchy_level": "task",
            "status_name": "Done",
            "status_category": "done",
            "created_at": now,
            "resolved_at": now,
            "lead_time_days": 3.5,
            "lead_time_hours": 84.0,
        }
        self.velocity_row = {
            "sprint_id": str(uuid4()),
            "sprint_external_id": "SPR-10",
            "sprint_name": "Sprint 10",
            "project_id": project_id,
            "project_key": "ADS",
            "project_name": "Ads Platform",
            "sprint_status": "closed",
            "start_date": date(2026, 1, 1),
            "end_date": date(2026, 1, 14),
            "complete_date": date(2026, 1, 14),
            "total_issues": 10,
            "completed_issues": 8,
            "completion_rate_pct": 80.0,
        }
        self.throughput_row = {
            "resolved_date": date(2026, 1, 12),
            "project_id": project_id,
            "project_key": "ADS",
            "project_name": "Ads Platform",
            "issue_type": None,
            "issues_completed": 6,
            "hierarchy_level": None,
            "avg_lead_time_days": None,
        }

    async def execute(self, query, params=None):
        sql = str(query)
        params = params or {}

        if "FROM platform.integration_types" in sql:
            return _FakeResult(scalars=[self.integration_type])

        if (
            "FROM platform.tool_integrations" in sql
            and "WHERE platform.tool_integrations.id" in sql
        ):
            return _FakeResult(one=None)

        if "FROM platform.tool_integrations" in sql:
            return _FakeResult(scalars=[self.integration])

        if "FROM platform.projects" in sql and "WHERE platform.projects.id" in sql:
            return _FakeResult(one=None)

        if "FROM platform.projects" in sql:
            return _FakeResult(scalars=[self.project])

        if "FROM metrics.v_facts vf" in sql:
            if "COUNT(*)" in sql:
                return _FakeResult(scalar_value=1)
            if "AVG(value) as avg_days" in sql:
                return _FakeResult(mappings=[{"avg_days": 3.5, "median_days": 3.0}])
            if "calc_code = 'lead_time_days'" in sql:
                return _FakeResult(mappings=[self.lead_time_row])
            if "metric_code = 'velocity'" in sql:
                return _FakeResult(mappings=[self.velocity_row])
            if "calc_code = 'throughput_count'" in sql:
                return _FakeResult(mappings=[self.throughput_row])

        return _FakeResult()

    async def commit(self):
        return None

    async def rollback(self):
        return None

    async def close(self):
        return None


@pytest.fixture
def api_client():
    fake_db = _FakeAsyncSession()

    async def _override_get_db():
        yield fake_db

    async def _override_admin():
        return AdminSession(
            user_id=str(uuid4()),
            email="admin@example.com",
            display_name="Admin",
            is_admin=True,
            expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
        )

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[require_admin] = _override_admin
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def unauth_api_client():
    fake_db = _FakeAsyncSession()

    async def _override_get_db():
        yield fake_db

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


class TestHealthEndpoint:
    def test_health_check(self, api_client):
        response = api_client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}

    def test_root_endpoint(self, api_client):
        response = api_client.get("/")
        assert response.status_code == 200
        body = response.json()
        assert body["docs"] == "/docs"
        assert body["health"] == "/health"
        assert "Process Metrics Platform API" in body["message"]


class TestIntegrationTypesEndpoint:
    def test_list_integration_types(self, api_client):
        response = api_client.get("/api/v1/integration-types")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "jira_cloud"
        assert data[0]["is_active"] is True
        UUID(data[0]["id"])


class TestIntegrationsEndpoint:
    def test_list_integrations_requires_auth(self, unauth_api_client):
        response = unauth_api_client.get("/api/v1/integrations")
        assert response.status_code == 401

    def test_list_integrations(self, api_client):
        response = api_client.get("/api/v1/integrations")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["integration_type_name"] == "jira_cloud"
        assert data[0]["instance_url"] == "https://jira.example.com"
        UUID(data[0]["id"])
        UUID(data[0]["user_id"])

    def test_list_integrations_with_filters(self, api_client):
        response = api_client.get("/api/v1/integrations", params={"is_active": True})
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["is_active"] is True

    def test_get_nonexistent_integration(self, api_client):
        response = api_client.get(
            "/api/v1/integrations/00000000-0000-0000-0000-000000000000"
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestProjectsEndpoint:
    def test_list_projects_requires_auth(self, unauth_api_client):
        response = unauth_api_client.get("/api/v1/projects")
        assert response.status_code == 401

    def test_list_projects(self, api_client):
        response = api_client.get("/api/v1/projects")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["external_key"] == "ADS"
        assert data[0]["name"] == "Ads Platform"
        UUID(data[0]["id"])

    def test_list_projects_with_filters(self, api_client):
        response = api_client.get("/api/v1/projects", params={"is_active": True})
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["is_active"] is True

    def test_get_nonexistent_project(self, api_client):
        response = api_client.get(
            "/api/v1/projects/00000000-0000-0000-0000-000000000000"
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestMetricsEndpoint:
    def test_get_metrics_config(self, api_client):
        response = api_client.get("/api/v1/metrics/config")
        assert response.status_code == 200
        data = response.json()
        assert data["commitment_statuses"]
        assert data["done_statuses"]
        assert data["estimation_field"] == "story_points"

    def test_update_metrics_config(self, api_client):
        response = api_client.put(
            "/api/v1/metrics/config",
            json={
                "commitment_statuses": ["In Progress"],
                "done_statuses": ["Done", "Closed"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["commitment_statuses"] == ["In Progress"]
        assert data["done_statuses"] == ["Done", "Closed"]

    def test_get_lead_time_metrics(self, api_client):
        response = api_client.get("/api/v1/metrics/lead-time")
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 1
        assert data["avg_lead_time_days"] == 3.5
        assert data["items"][0]["issue_key"] == "ADS-42"
        assert data["items"][0]["lead_time_hours"] == 84.0

    def test_get_lead_time_with_filters(self, api_client):
        response = api_client.get(
            "/api/v1/metrics/lead-time", params={"issue_type": "Story", "limit": 10}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 1
        assert data["items"][0]["issue_type"] == "Story"

    def test_get_velocity_metrics(self, api_client):
        response = api_client.get("/api/v1/metrics/velocity")
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 1
        assert data["items"][0]["completion_rate_pct"] == 80.0
        assert data["items"][0]["completed_issues"] == 8

    def test_get_throughput_metrics(self, api_client):
        response = api_client.get("/api/v1/metrics/throughput")
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 1
        assert data["total_issues_completed"] == 6
        assert data["items"][0]["issue_type"] == "Total"


class TestAPIDocumentation:
    def test_openapi_json(self, api_client):
        response = api_client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert data["openapi"].startswith("3.")
        assert "/api/v1/integrations" in data["paths"]

    def test_docs_page(self, api_client):
        response = api_client.get("/docs")
        assert response.status_code == 200

    def test_redoc_page(self, api_client):
        response = api_client.get("/redoc")
        assert response.status_code == 200
