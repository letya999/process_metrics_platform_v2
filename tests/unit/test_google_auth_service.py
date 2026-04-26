import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException

from app.services import google_auth
from app.services.admin_auth import _b64url_decode


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("ADMIN_AUTH_SECRET", "test-secret-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv(
        "ADMIN_GOOGLE_REDIRECT_URI",
        "http://localhost:8000/api/v1/admin/auth/google/callback",
    )
    monkeypatch.setenv("ADMIN_UI_URL", "http://localhost:8501")


def test_build_google_redirect_url_returns_google_domain():
    url = google_auth.build_google_redirect_url("http://localhost:8501")
    assert url.startswith("https://accounts.google.com")


def test_build_google_redirect_url_contains_client_id():
    url = google_auth.build_google_redirect_url("http://localhost:8501")
    assert "client_id=test-client-id" in url


def test_build_google_redirect_url_contains_state():
    url = google_auth.build_google_redirect_url("http://localhost:8501")
    assert "state=" in url


def test_build_google_redirect_url_rejects_open_redirect():
    # If return_to is suspicious, it should fallback to ADMIN_UI_URL
    url = google_auth.build_google_redirect_url("https://evil.com/steal")
    # State contains the return_to URL
    state_encoded = url.split("state=")[1].split("&")[0].split(".")[0]
    payload = json.loads(_b64url_decode(state_encoded))
    assert payload["return_to"] == "http://localhost:8501"


def test_build_google_redirect_url_raises_503_when_no_client_id(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    with pytest.raises(HTTPException) as exc:
        google_auth.build_google_redirect_url("http://localhost:8501")
    assert exc.value.status_code == 503


def test_verify_state_roundtrip():
    return_url = "http://localhost:8501/custom"
    url = google_auth.build_google_redirect_url(return_url)
    state = url.split("state=")[1].split("&")[0]

    verified_url = google_auth.verify_state_and_get_return_to(state)
    assert verified_url == return_url


def test_verify_state_returns_none_for_tampered_state():
    url = google_auth.build_google_redirect_url("http://localhost:8501")
    state = url.split("state=")[1].split("&")[0]

    # Tamper with the signature (last character)
    tampered_state = state[:-1] + ("0" if state[-1] != "0" else "1")
    assert google_auth.verify_state_and_get_return_to(tampered_state) is None


def test_verify_state_returns_none_for_expired_state():
    with patch("time.time") as mock_time:
        now = 1000000
        mock_time.return_value = now
        url = google_auth.build_google_redirect_url("http://localhost:8501")
        state = url.split("state=")[1].split("&")[0]

        # Advance time by 11 minutes (660 seconds)
        mock_time.return_value = now + 660
        assert google_auth.verify_state_and_get_return_to(state) is None


def test_verify_state_returns_none_for_garbage():
    assert google_auth.verify_state_and_get_return_to("notavalidstate") is None
    assert google_auth.verify_state_and_get_return_to("no.dots.here") is None
    assert google_auth.verify_state_and_get_return_to("too.many.dots.here") is None


def _make_httpx_mock(
    token_status=200, token_body=None, tokeninfo_status=200, tokeninfo_body=None
):
    if token_body is None:
        token_body = {"id_token": "fake.id.token"}
    if tokeninfo_body is None:
        tokeninfo_body = {"email": "user@example.com", "email_verified": "true"}

    mock_client = MagicMock()

    # Mock post for token endpoint
    mock_token_resp = MagicMock()
    mock_token_resp.status_code = token_status
    mock_token_resp.json.return_value = token_body
    mock_client.post = AsyncMock(return_value=mock_token_resp)

    # Mock get for tokeninfo endpoint
    mock_info_resp = MagicMock()
    mock_info_resp.status_code = tokeninfo_status
    mock_info_resp.json.return_value = tokeninfo_body
    mock_client.get = AsyncMock(return_value=mock_info_resp)

    # Mock AsyncClient context manager
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    return mock_client


@pytest.mark.asyncio
async def test_exchange_code_returns_email_on_success():
    mock_client = _make_httpx_mock()
    with patch("app.services.google_auth.httpx.AsyncClient", return_value=mock_client):
        email = await google_auth.exchange_code_for_email("code123")
        assert email == "user@example.com"


@pytest.mark.asyncio
async def test_exchange_code_returns_none_when_token_endpoint_fails():
    mock_client = _make_httpx_mock(token_status=400)
    with patch("app.services.google_auth.httpx.AsyncClient", return_value=mock_client):
        email = await google_auth.exchange_code_for_email("code123")
        assert email is None


@pytest.mark.asyncio
async def test_exchange_code_returns_none_when_no_id_token():
    mock_client = _make_httpx_mock(token_body={})
    with patch("app.services.google_auth.httpx.AsyncClient", return_value=mock_client):
        email = await google_auth.exchange_code_for_email("code123")
        assert email is None


@pytest.mark.asyncio
async def test_exchange_code_returns_none_when_tokeninfo_fails():
    mock_client = _make_httpx_mock(tokeninfo_status=400)
    with patch("app.services.google_auth.httpx.AsyncClient", return_value=mock_client):
        email = await google_auth.exchange_code_for_email("code123")
        assert email is None


@pytest.mark.asyncio
async def test_exchange_code_returns_none_when_email_not_verified():
    mock_client = _make_httpx_mock(
        tokeninfo_body={"email": "u@x", "email_verified": "false"}
    )
    with patch("app.services.google_auth.httpx.AsyncClient", return_value=mock_client):
        email = await google_auth.exchange_code_for_email("code123")
        assert email is None


@pytest.mark.asyncio
async def test_exchange_code_returns_none_when_no_client_id(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    email = await google_auth.exchange_code_for_email("code123")
    assert email is None


@pytest.mark.asyncio
async def test_exchange_code_returns_none_on_network_exception():
    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=httpx.RequestError("network error"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.google_auth.httpx.AsyncClient", return_value=mock_client):
        email = await google_auth.exchange_code_for_email("code123")
        assert email is None
