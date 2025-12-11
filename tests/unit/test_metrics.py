"""Tests for metrics API endpoints."""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app


class TestMetricsConfig:
    """Tests for metrics configuration endpoints."""

    def test_get_metrics_config(self, mock_db_session):
        """Test getting metrics configuration."""

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        response = client.get("/api/v1/metrics/config")

        assert response.status_code == 200
        data = response.json()
        assert "commitment_statuses" in data
        assert "done_statuses" in data
        assert "estimation_field" in data
        assert "lead_time_start_status" in data
        assert "lead_time_end_status" in data
        app.dependency_overrides.clear()

    def test_update_metrics_config(self, mock_db_session):
        """Test updating metrics configuration."""

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        response = client.put(
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
        app.dependency_overrides.clear()


class TestLeadTimeMetrics:
    """Tests for lead time metrics endpoint."""

    def test_get_lead_time_empty(self, mock_db_session):
        """Test getting lead time metrics when no data exists."""
        # Mock empty result for data query
        mock_data_result = MagicMock()
        mock_data_result.mappings.return_value.all.return_value = []

        # Mock count query result
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0

        # Mock avg query result
        mock_avg_result = MagicMock()
        mock_avg_result.mappings.return_value.first.return_value = {
            "avg_days": None,
            "median_days": None,
        }

        # Set up execute to return different results for different calls
        mock_db_session.execute.side_effect = [
            mock_data_result,
            mock_count_result,
            mock_avg_result,
        ]

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        response = client.get("/api/v1/metrics/lead-time")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total_count"] == 0
        app.dependency_overrides.clear()

    def test_get_lead_time_with_filters(self, mock_db_session, sample_project_id):
        """Test getting lead time metrics with filters."""
        # Mock empty result (filter returns no data)
        mock_data_result = MagicMock()
        mock_data_result.mappings.return_value.all.return_value = []

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0

        mock_avg_result = MagicMock()
        mock_avg_result.mappings.return_value.first.return_value = {
            "avg_days": None,
            "median_days": None,
        }

        mock_db_session.execute.side_effect = [
            mock_data_result,
            mock_count_result,
            mock_avg_result,
        ]

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        response = client.get(
            f"/api/v1/metrics/lead-time?project_id={sample_project_id}&issue_type=Story"
        )

        assert response.status_code == 200
        app.dependency_overrides.clear()


class TestVelocityMetrics:
    """Tests for velocity metrics endpoint."""

    def test_get_velocity_empty(self, mock_db_session):
        """Test getting velocity metrics when no data exists."""
        # Mock empty result
        mock_data_result = MagicMock()
        mock_data_result.mappings.return_value.all.return_value = []

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0

        mock_avg_result = MagicMock()
        mock_avg_result.mappings.return_value.first.return_value = {
            "avg_completion_rate": None,
            "avg_issues": None,
        }

        mock_db_session.execute.side_effect = [
            mock_data_result,
            mock_count_result,
            mock_avg_result,
        ]

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        response = client.get("/api/v1/metrics/velocity")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total_count"] == 0
        app.dependency_overrides.clear()

    def test_get_velocity_with_filters(self, mock_db_session, sample_project_id):
        """Test getting velocity metrics with filters."""
        mock_data_result = MagicMock()
        mock_data_result.mappings.return_value.all.return_value = []

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0

        mock_avg_result = MagicMock()
        mock_avg_result.mappings.return_value.first.return_value = {
            "avg_completion_rate": None,
            "avg_issues": None,
        }

        mock_db_session.execute.side_effect = [
            mock_data_result,
            mock_count_result,
            mock_avg_result,
        ]

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        response = client.get(
            f"/api/v1/metrics/velocity?project_id={sample_project_id}&sprint_status=closed"
        )

        assert response.status_code == 200
        app.dependency_overrides.clear()


class TestThroughputMetrics:
    """Tests for throughput metrics endpoint."""

    def test_get_throughput_empty(self, mock_db_session):
        """Test getting throughput metrics when no data exists."""
        mock_data_result = MagicMock()
        mock_data_result.mappings.return_value.all.return_value = []

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0

        mock_sum_result = MagicMock()
        mock_sum_result.mappings.return_value.first.return_value = {
            "total_completed": 0,
            "avg_daily": None,
        }

        mock_db_session.execute.side_effect = [
            mock_data_result,
            mock_count_result,
            mock_sum_result,
        ]

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        response = client.get("/api/v1/metrics/throughput")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total_count"] == 0
        assert data["total_issues_completed"] == 0
        app.dependency_overrides.clear()

    def test_get_throughput_with_date_filters(self, mock_db_session):
        """Test getting throughput metrics with date filters."""
        mock_data_result = MagicMock()
        mock_data_result.mappings.return_value.all.return_value = []

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0

        mock_sum_result = MagicMock()
        mock_sum_result.mappings.return_value.first.return_value = {
            "total_completed": 0,
            "avg_daily": None,
        }

        mock_db_session.execute.side_effect = [
            mock_data_result,
            mock_count_result,
            mock_sum_result,
        ]

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        response = client.get(
            "/api/v1/metrics/throughput?date_from=2024-01-01&date_to=2024-12-31"
        )

        assert response.status_code == 200
        app.dependency_overrides.clear()


class TestRefreshMetrics:
    """Tests for metrics refresh endpoint."""

    def test_refresh_metrics_success(self, mock_db_session):
        """Test triggering metrics refresh."""
        mock_db_session.execute.return_value = None

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        response = client.post("/api/v1/metrics/refresh")

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "success"
        app.dependency_overrides.clear()

    def test_refresh_metrics_view_not_found(self, mock_db_session):
        """Test refreshing metrics when views don't exist."""
        mock_db_session.execute.side_effect = Exception(
            "relation metrics.refresh_all_views does not exist"
        )

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        response = client.post("/api/v1/metrics/refresh")

        assert response.status_code == 404
        app.dependency_overrides.clear()
