from contextlib import asynccontextmanager

from fastapi.testclient import TestClient

from app.main import app


@asynccontextmanager
async def _healthy_db_context():
    class _DB:
        async def execute(self, _query):
            return None

    yield _DB()


@asynccontextmanager
async def _broken_db_context():
    raise RuntimeError("db down")
    yield


def test_health_check_liveness():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_readiness_check_healthy(monkeypatch):
    monkeypatch.setattr("app.api.health.get_db_context", _healthy_db_context)

    client = TestClient(app)
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_readiness_check_unhealthy(monkeypatch):
    monkeypatch.setattr("app.api.health.get_db_context", _broken_db_context)

    client = TestClient(app)
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "unhealthy"
