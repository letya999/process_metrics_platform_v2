import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

# Mock DB initialization to avoid real connection attempts during import/test
with patch("app.main.init_db", new_callable=AsyncMock):
    with patch("app.main.close_db", new_callable=AsyncMock):
        from app.main import app, lifespan


def test_app_initialization():
    """Verify app is initialized correctly."""
    assert app.title == "Process Metrics Platform"
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "message" in response.json()


def test_app_cors_origins():
    """Check that CORS origins are set."""
    from app.main import ALLOWED_ORIGINS

    assert (
        "http://localhost:8000" in ALLOWED_ORIGINS
        or os.getenv("ENVIRONMENT") == "production"
    )


@pytest.mark.asyncio
async def test_lifespan_continues_when_init_db_fails():
    with (
        patch("app.main.init_db", new=AsyncMock(side_effect=RuntimeError("db down"))),
        patch("app.main.close_db", new=AsyncMock()),
    ):
        async with lifespan(app):
            assert True


@pytest.mark.asyncio
async def test_lifespan_tolerates_close_db_failure():
    with (
        patch("app.main.init_db", new=AsyncMock()),
        patch(
            "app.main.close_db",
            new=AsyncMock(side_effect=RuntimeError("dispose failed")),
        ),
    ):
        async with lifespan(app):
            assert True
