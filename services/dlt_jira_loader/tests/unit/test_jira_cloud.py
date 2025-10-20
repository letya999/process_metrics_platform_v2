from typing import Any, Dict

import pytest
import requests
import responses

from services.dlt_jira_loader.dlt_sources import jira_cloud


@pytest.fixture
def mock_client(monkeypatch):
    class DummyClient:
        def __init__(self, base_url: str = "https://example.atlassian.net"):
            self.base_url = base_url

        def search_issues(self, jql, start_at=0, max_results=50):
            # allow tests to simulate different project keys via the JQL, but
            # fall back to a simple payload when responses stubs are not present
            params = {"jql": jql, "startAt": start_at, "maxResults": max_results}
            resp = requests.get(f"{self.base_url}/rest/api/3/search", params=params)
            try:
                return resp.json()
            except ValueError:
                # fallback for older DummyClient behavior
                return issues_payload("PROJ", 1)

        def get_comments(self, issue_key, start_at=0, max_results=50):
            params = {"startAt": start_at, "maxResults": max_results}
            resp = requests.get(
                f"{self.base_url}/rest/api/3/issue/{issue_key}/comment", params=params
            )
            return resp.json()

        def get_sprints(self, board_id, start_at=0, max_results=50):
            params = {"startAt": start_at, "maxResults": max_results}
            resp = requests.get(
                f"{self.base_url}/rest/agile/1.0/board/{board_id}/sprint", params=params
            )
            return resp.json()

    monkeypatch.setenv("JIRA_INSTANCE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_USER_EMAIL", "bot@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "token123")
    return DummyClient()


# --- Fixtures and helpers -------------------------------------------------


@pytest.fixture(autouse=True)
def env_credentials(monkeypatch):
    """Ensure credentials resolved from env by default in tests."""
    monkeypatch.setenv("JIRA_INSTANCE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_USER_EMAIL", "bot@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "token123")
    yield


def issues_payload(project_key: str, count: int = 1) -> Dict[str, Any]:
    return {
        "startAt": 0,
        "maxResults": 50,
        "total": count,
        "issues": [
            {
                "id": str(10000 + i),
                "key": f"{project_key}-{i+1}",
                "fields": {"summary": f"Issue {i+1}"},
            }
            for i in range(count)
        ],
    }


def comments_payload(count: int = 1) -> Dict[str, Any]:
    return {
        "startAt": 0,
        "maxResults": 50,
        "total": count,
        "comments": [
            {
                "id": f"c{i+1}",
                "body": f"comment {i+1}",
                "created": "2025-01-01T00:00:00.000+0000",
                "author": {"displayName": "Bot"},
            }
            for i in range(count)
        ],
    }


def add_search_stub(project_key: str, payload: Dict[str, Any]) -> None:
    responses.add(
        responses.GET,
        "https://example.atlassian.net/rest/api/3/search",
        json=payload,
        status=200,
    )


def add_comments_stub(issue_key: str, payload: Dict[str, Any]) -> None:
    responses.add(
        responses.GET,
        f"https://example.atlassian.net/rest/api/3/issue/{issue_key}/comment",
        json=payload,
        status=200,
    )


# --- Tests ---------------------------------------------------------------


@responses.activate
def test_iterate_single_issue_and_comment(mock_client):
    project_key = "PROJ"
    add_search_stub(project_key, issues_payload(project_key, count=1))
    add_comments_stub(f"{project_key}-1", comments_payload(count=1))

    # construct resources directly using factories to avoid dlt.source wrapping
    client = mock_client
    issues_res = jira_cloud.make_issues_resource(project_key=project_key, client=client)
    comments_res = jira_cloud.make_comments_resource(client=client)

    issues = list(issues_res())
    assert len(issues) == 1
    assert issues[0]["issue_key"] == "PROJ-1"

    comments = list(comments_res(issue_key="PROJ-1"))
    assert len(comments) == 1
    assert comments[0]["comment_id"] == "c1"


@responses.activate
def test_pagination_multiple_issues_and_comments(mock_client):
    project_key = "BIG"

    # simulate server returning multiple pages: first page with 2 items, second empty
    responses.add(
        responses.GET,
        "https://example.atlassian.net/rest/api/3/search",
        json=issues_payload(project_key, count=2),
        status=200,
    )
    # comments for each issue
    add_comments_stub(f"{project_key}-1", comments_payload(count=2))
    add_comments_stub(f"{project_key}-2", comments_payload(count=1))

    client = mock_client
    issues_res = jira_cloud.make_issues_resource(project_key=project_key, client=client)
    comments_res = jira_cloud.make_comments_resource(client=client)

    issues = list(issues_res())
    assert len(issues) == 2

    all_comments = []
    for issue in issues:
        all_comments.extend(list(comments_res(issue_key=issue["issue_key"])))
    assert len(all_comments) >= 3


@responses.activate
def test_created_after_filter_returns_empty_when_no_issues(mock_client):
    project_key = "PROJ"
    responses.add(
        responses.GET,
        "https://example.atlassian.net/rest/api/3/search",
        json={"startAt": 0, "maxResults": 50, "total": 0, "issues": []},
        status=200,
    )

    client = mock_client
    issues_res = jira_cloud.make_issues_resource(project_key=project_key, client=client)
    issues = list(issues_res(created_after="2024-01-01"))
    assert issues == []


@responses.activate
def test_sprints_resource_iteration(mock_client):
    # sprints endpoint uses agile API path; simulate a simple response
    board_id = 42
    responses.add(
        responses.GET,
        f"https://example.atlassian.net/rest/agile/1.0/board/{board_id}/sprint",
        json={
            "startAt": 0,
            "maxResults": 50,
            "values": [{"id": 1, "name": "S1", "state": "active"}],
        },
        status=200,
    )

    client = mock_client
    sprints_res = jira_cloud.make_sprints_resource(client=client)
    sprints = list(sprints_res(board_id=board_id))
    assert len(sprints) == 1
    assert sprints[0]["sprint_id"] == 1


@responses.activate
def test_error_on_missing_credentials(monkeypatch):
    # clear env vars to simulate missing credentials
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    monkeypatch.delenv("JIRA_USER_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_INSTANCE_URL", raising=False)

    with pytest.raises(ValueError):
        _ = jira_cloud.jira_source(project_key="PROJ", config={})
