import pytest

from services.dlt_jira_loader.dlt_sources import jira_cloud


def test_error_on_missing_credentials(monkeypatch):
    # clear env vars to simulate missing credentials
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    monkeypatch.delenv("JIRA_USER_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_INSTANCE_URL", raising=False)

    with pytest.raises(ValueError):
        _ = jira_cloud.jira_source(project_key="PROJ", config={})
