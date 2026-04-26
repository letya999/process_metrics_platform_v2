from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.responses import RedirectResponse
from starlette.requests import Request

from app.api import admin as admin_api
from app.services.admin_auth import get_session


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


def _make_db():
    db = MagicMock()
    db.execute = AsyncMock()
    return db


def _make_request(path="/api/v1/admin/auth/google/redirect"):
    scope = {
        "type": "http",
        "client": ("127.0.0.1", 123),
        "path": path,
    }
    return Request(scope)


def _mappings_result(*, first=None):
    result = MagicMock()
    mappings = MagicMock()
    mappings.first.return_value = first
    result.mappings.return_value = mappings
    return result


@pytest.mark.asyncio
async def test_google_redirect_returns_302_to_google():
    request = _make_request()
    response = await admin_api.admin_google_redirect(
        request, return_to="http://localhost:8501/custom"
    )
    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302
    assert response.headers["location"].startswith("https://accounts.google.com")
    assert "state=" in response.headers["location"]


@pytest.mark.asyncio
async def test_google_redirect_uses_default_admin_ui_url_when_return_to_is_none():
    request = _make_request()
    response = await admin_api.admin_google_redirect(request, return_to=None)
    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302
    assert response.headers["location"].startswith("https://accounts.google.com")


@pytest.mark.asyncio
async def test_google_redirect_raises_503_when_google_not_configured(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    request = _make_request()
    with pytest.raises(HTTPException) as exc:
        await admin_api.admin_google_redirect(request)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_google_callback_issues_jwt_and_redirects_on_success(monkeypatch):
    db = _make_db()
    user_id = uuid4()
    row = {
        "id": user_id,
        "email": "admin@example.com",
        "display_name": "Admin",
        "is_admin": True,
        "is_active": True,
    }
    db.execute.return_value = _mappings_result(first=row)

    request = _make_request("/api/v1/admin/auth/google/callback")

    # Patch service calls
    with (
        patch(
            "app.api.admin.verify_state_and_get_return_to",
            return_value="http://localhost:8501/ok",
        ),
        patch(
            "app.api.admin.exchange_code_for_email", new_callable=AsyncMock
        ) as mock_exchange,
    ):

        mock_exchange.return_value = "admin@example.com"

        response = await admin_api.admin_google_callback(
            request, db, code="code123", state="state123"
        )

        assert isinstance(response, RedirectResponse)
        location = response.headers["location"]
        assert location.startswith("http://localhost:8501/ok")

        parsed_url = urlparse(location)
        query = parse_qs(parsed_url.query)
        assert "token" in query
        token = query["token"][0]

        # Verify token
        session = get_session(token)
        assert session is not None
        assert session.email == "admin@example.com"
        assert session.user_id == str(user_id)


@pytest.mark.asyncio
async def test_google_callback_redirects_with_error_when_code_missing():
    db = _make_db()
    request = _make_request("/api/v1/admin/auth/google/callback")
    response = await admin_api.admin_google_callback(
        request, db, code=None, state="state123"
    )

    assert isinstance(response, RedirectResponse)
    assert "error=google_auth_cancelled" in response.headers["location"]


@pytest.mark.asyncio
async def test_google_callback_redirects_with_error_when_state_invalid():
    db = _make_db()
    request = _make_request("/api/v1/admin/auth/google/callback")

    with patch("app.api.admin.verify_state_and_get_return_to", return_value=None):
        response = await admin_api.admin_google_callback(
            request, db, code="code123", state="badstate"
        )

    assert isinstance(response, RedirectResponse)
    assert "error=google_auth_invalid_state" in response.headers["location"]


@pytest.mark.asyncio
async def test_google_callback_redirects_with_error_when_email_exchange_fails():
    db = _make_db()
    request = _make_request("/api/v1/admin/auth/google/callback")

    with (
        patch(
            "app.api.admin.verify_state_and_get_return_to",
            return_value="http://localhost:8501/ok",
        ),
        patch(
            "app.api.admin.exchange_code_for_email", new_callable=AsyncMock
        ) as mock_exchange,
    ):

        mock_exchange.return_value = None

        response = await admin_api.admin_google_callback(
            request, db, code="code123", state="state123"
        )

    assert isinstance(response, RedirectResponse)
    assert "error=google_auth_failed" in response.headers["location"]


@pytest.mark.asyncio
async def test_google_callback_redirects_with_error_when_user_not_found():
    db = _make_db()
    db.execute.return_value = _mappings_result(first=None)
    request = _make_request("/api/v1/admin/auth/google/callback")

    with (
        patch(
            "app.api.admin.verify_state_and_get_return_to",
            return_value="http://localhost:8501/ok",
        ),
        patch(
            "app.api.admin.exchange_code_for_email", new_callable=AsyncMock
        ) as mock_exchange,
    ):

        mock_exchange.return_value = "unknown@example.com"

        response = await admin_api.admin_google_callback(
            request, db, code="code123", state="state123"
        )

    assert isinstance(response, RedirectResponse)
    assert "error=google_auth_not_authorized" in response.headers["location"]


@pytest.mark.asyncio
async def test_google_callback_redirects_with_error_when_user_not_admin():
    db = _make_db()
    db.execute.return_value = _mappings_result(
        first={
            "id": uuid4(),
            "email": "a@x",
            "display_name": "A",
            "is_admin": False,
            "is_active": True,
        }
    )
    request = _make_request("/api/v1/admin/auth/google/callback")

    with (
        patch(
            "app.api.admin.verify_state_and_get_return_to",
            return_value="http://localhost:8501/ok",
        ),
        patch(
            "app.api.admin.exchange_code_for_email", new_callable=AsyncMock
        ) as mock_exchange,
    ):

        mock_exchange.return_value = "a@x"

        response = await admin_api.admin_google_callback(
            request, db, code="code123", state="state123"
        )

    assert isinstance(response, RedirectResponse)
    assert "error=google_auth_not_authorized" in response.headers["location"]


@pytest.mark.asyncio
async def test_google_callback_redirects_with_error_when_user_inactive():
    db = _make_db()
    db.execute.return_value = _mappings_result(
        first={
            "id": uuid4(),
            "email": "a@x",
            "display_name": "A",
            "is_admin": True,
            "is_active": False,
        }
    )
    request = _make_request("/api/v1/admin/auth/google/callback")

    with (
        patch(
            "app.api.admin.verify_state_and_get_return_to",
            return_value="http://localhost:8501/ok",
        ),
        patch(
            "app.api.admin.exchange_code_for_email", new_callable=AsyncMock
        ) as mock_exchange,
    ):

        mock_exchange.return_value = "a@x"

        response = await admin_api.admin_google_callback(
            request, db, code="code123", state="state123"
        )

    assert isinstance(response, RedirectResponse)
    assert "error=google_auth_not_authorized" in response.headers["location"]


@pytest.mark.asyncio
async def test_google_callback_google_error_param_triggers_cancelled_redirect():
    db = _make_db()
    request = _make_request("/api/v1/admin/auth/google/callback")
    response = await admin_api.admin_google_callback(request, db, error="access_denied")

    assert isinstance(response, RedirectResponse)
    assert "error=google_auth_cancelled" in response.headers["location"]
