from uuid import UUID

from services.dlt_jira_loader.dlt_sources.jira_cloud import jira_source
from services.dlt_jira_loader.flows.tasks.extract import prepare_resources
from services.dlt_jira_loader.models.config import ProjectWithCredentials


class DummyClient:
    def __init__(self):
        self.called = {}

    def find_boards(self, project_key=None):
        return {"values": [{"id": 1, "name": "B", "type": "scrum"}]}

    def get_comments(self, issue_key, start_at=0, max_results=50):
        return {"comments": []}

    def search_issues(self, jql, start_at=0, max_results=50):
        return {"issues": []}

    def get_sprints(self, board_id, start_at=0, max_results=50):
        return {"values": []}

    def get_project_versions(self, project_key):
        return []


def test_jira_source_and_prepare(monkeypatch):
    # monkeypatch resolve to avoid env access and inject our client
    def fake_resolve(cfg, key, env_key):
        mapping = {"instance_url": "https://x", "user_email": "u@x", "api_token": "t"}
        return mapping[key]

    monkeypatch.setattr(
        "services.dlt_jira_loader.dlt_sources.jira_cloud.resolve_from_env_or_config",
        fake_resolve,
    )

    resources = jira_source("PRJ", {})
    # jira_source returns a tuple of callables
    assert len(resources) >= 4

    # test prepare_resources merges overrides and returns mapping
    project = ProjectWithCredentials(
        project_id=UUID("11111111-1111-1111-1111-111111111111"),
        external_id="1",
        external_key="PRJ",
        credentials={},
    )

    monkeypatch.setattr(
        "services.dlt_jira_loader.dlt_sources.jira_cloud.JiraClient",
        lambda instance_url, api_token, email: DummyClient(),
    )

    res_mapping = prepare_resources.fn(
        project, "2025-01-01T00:00:00", "2025-01-02T00:00:00", None
    )
    assert "issues" in res_mapping and "boards" in res_mapping
