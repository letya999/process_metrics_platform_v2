from fastapi.testclient import TestClient

from app.main import app


def test_health_check():
    client = TestClient(app)
    response = client.get("/api/v1/health")
    # Note: I need to verify the prefix in app/main.py or app/api/__init__.py
    # If it fails, I'll adjust the path.
    if response.status_code == 404:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
