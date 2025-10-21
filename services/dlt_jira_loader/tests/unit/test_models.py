from uuid import UUID

import pytest

from services.dlt_jira_loader.models.config import (
    JiraSyncConfig,
    ProjectWithCredentials,
)


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
