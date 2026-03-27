from types import SimpleNamespace

import pytest

from streamlit_admin.client import AdminApiClient


def test_client_base_url_from_env(monkeypatch):
    monkeypatch.setenv("ADMIN_API_URL", "http://example.local/api/")

    client = AdminApiClient()

    assert client.base_url == "http://example.local/api"


def test_headers_with_and_without_token():
    client = AdminApiClient(base_url="http://localhost:8000")

    assert client._headers() == {"Content-Type": "application/json"}
    assert client._headers("abc") == {
        "Content-Type": "application/json",
        "Authorization": "Bearer abc",
    }


def test_request_success_returns_json(monkeypatch):
    client = AdminApiClient(base_url="http://localhost:8000")

    def _fake_request(**kwargs):
        assert kwargs["method"] == "GET"
        assert kwargs["url"] == "http://localhost:8000/admin/ping"
        assert kwargs["headers"]["Authorization"] == "Bearer token"
        assert kwargs["timeout"] == 30
        return SimpleNamespace(ok=True, text='{"ok": true}', json=lambda: {"ok": True})

    monkeypatch.setattr("streamlit_admin.client.requests.request", _fake_request)

    result = client.request("GET", "/admin/ping", token="token")

    assert result == {"ok": True}


def test_request_success_empty_body_returns_none(monkeypatch):
    client = AdminApiClient(base_url="http://localhost:8000")

    monkeypatch.setattr(
        "streamlit_admin.client.requests.request",
        lambda **_kwargs: SimpleNamespace(ok=True, text="", json=lambda: None),
    )

    assert client.request("GET", "/admin/ping") is None


def test_request_raises_runtime_error_on_non_ok(monkeypatch):
    client = AdminApiClient(base_url="http://localhost:8000")

    monkeypatch.setattr(
        "streamlit_admin.client.requests.request",
        lambda **_kwargs: SimpleNamespace(ok=False, status_code=403, text="denied"),
    )

    with pytest.raises(RuntimeError, match="403: denied"):
        client.request("GET", "/admin/ping")
