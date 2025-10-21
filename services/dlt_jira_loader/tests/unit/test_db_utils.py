from services.dlt_jira_loader.utils.db import resolve_api_token


def test_resolve_api_token_prefers_env(monkeypatch):
    monkeypatch.setenv("SECRET_TOKEN_NAME", "envtoken")
    row = {
        "secret_provider": "env",
        "secret_reference": "SECRET_TOKEN_NAME",
        "api_token_unsafe": "unsafe",
    }
    token = resolve_api_token(row)
    assert token == "envtoken"


def test_resolve_api_token_fallback_to_unsafe():
    row = {"api_token_unsafe": "unsafevalue"}
    token = resolve_api_token(row)
    assert token == "unsafevalue"


def test_resolve_api_token_error_on_missing():
    import pytest

    with pytest.raises(ValueError):
        resolve_api_token({})
