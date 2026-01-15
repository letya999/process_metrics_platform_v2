"""Integration tests for FastAPI endpoints.

Tests the API endpoints in app/api/
"""


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_check(self, api_client):
        """Test health endpoint returns 200."""
        response = api_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_root_endpoint(self, api_client):
        """Test root endpoint."""
        response = api_client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "docs" in data


class TestIntegrationTypesEndpoint:
    """Tests for integration types endpoint."""

    def test_list_integration_types(self, api_client):
        """Test listing integration types."""
        response = api_client.get("/api/v1/integration-types")

        # May return empty list if DB not populated
        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestIntegrationsEndpoint:
    """Tests for integrations CRUD endpoints."""

    def test_list_integrations(self, api_client):
        """Test listing integrations."""
        response = api_client.get("/api/v1/integrations")

        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_list_integrations_with_filters(self, api_client):
        """Test listing integrations with filter parameters."""
        response = api_client.get(
            "/api/v1/integrations",
            params={"is_active": True},
        )

        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_get_nonexistent_integration(self, api_client):
        """Test getting non-existent integration returns 404."""
        response = api_client.get(
            "/api/v1/integrations/00000000-0000-0000-0000-000000000000"
        )

        assert response.status_code == 404


class TestProjectsEndpoint:
    """Tests for projects CRUD endpoints."""

    def test_list_projects(self, api_client):
        """Test listing projects."""
        response = api_client.get("/api/v1/projects")

        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_list_projects_with_filters(self, api_client):
        """Test listing projects with filter parameters."""
        response = api_client.get(
            "/api/v1/projects",
            params={"is_active": True},
        )

        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_get_nonexistent_project(self, api_client):
        """Test getting non-existent project returns 404."""
        response = api_client.get(
            "/api/v1/projects/00000000-0000-0000-0000-000000000000"
        )

        assert response.status_code == 404


class TestMetricsEndpoint:
    """Tests for metrics endpoints."""

    def test_get_metrics_config(self, api_client):
        """Test getting metrics configuration."""
        response = api_client.get("/api/v1/metrics/config")

        assert response.status_code == 200
        data = response.json()
        assert "commitment_statuses" in data
        assert "done_statuses" in data

    def test_update_metrics_config(self, api_client):
        """Test updating metrics configuration."""
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

    def test_get_lead_time_metrics(self, api_client):
        """Test getting lead time metrics."""
        response = api_client.get("/api/v1/metrics/lead-time")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total_count" in data

    def test_get_lead_time_with_filters(self, api_client):
        """Test getting lead time metrics with filters."""
        response = api_client.get(
            "/api/v1/metrics/lead-time",
            params={"issue_type": "Story", "limit": 10},
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    def test_get_velocity_metrics(self, api_client):
        """Test getting velocity metrics."""
        response = api_client.get("/api/v1/metrics/velocity")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total_count" in data

    def test_get_throughput_metrics(self, api_client):
        """Test getting throughput metrics."""
        response = api_client.get("/api/v1/metrics/throughput")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total_count" in data


class TestAPIDocumentation:
    """Tests for API documentation endpoints."""

    def test_openapi_json(self, api_client):
        """Test OpenAPI JSON is accessible."""
        response = api_client.get("/openapi.json")

        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data
        assert "paths" in data

    def test_docs_page(self, api_client):
        """Test Swagger UI docs page is accessible."""
        response = api_client.get("/docs")

        assert response.status_code == 200

    def test_redoc_page(self, api_client):
        """Test ReDoc page is accessible."""
        response = api_client.get("/redoc")

        assert response.status_code == 200
