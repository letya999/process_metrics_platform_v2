import os
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

# Mock DB initialization to avoid real connection attempts during import/test
with patch("app.main.init_db", new_callable=AsyncMock):
    with patch("app.main.close_db", new_callable=AsyncMock):
        from app.main import app


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
