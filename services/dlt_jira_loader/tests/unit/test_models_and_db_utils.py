from uuid import UUID

import pytest

from services.dlt_jira_loader.models.config import (
    JiraSyncConfig,
    ProjectWithCredentials,
)
from services.dlt_jira_loader.utils.db import resolve_api_token


def test_project_with_credentials_model_roundtrip():
    p = ProjectWithCredentials(
        project_id=UUID("11111111-1111-1111-1111-111111111111"),
        external_id="100",
        external_key="PROJ",
        name="Test",
        credentials={"user_email": "bot@example.com"},
    )
    assert p.external_key == "PROJ"


def test_jira_sync_config_forbids_extra_fields():
    # Pydantic v2 raises ValidationError for extra inputs; assert accordingly
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        JiraSyncConfig(
            project_uuids=[UUID("11111111-1111-1111-1111-111111111111")], unknown=1
        )


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
    with pytest.raises(ValueError):
        resolve_api_token({})
