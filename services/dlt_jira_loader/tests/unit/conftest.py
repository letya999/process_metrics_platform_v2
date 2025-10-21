from typing import Any, Dict

import pytest
import requests
import responses


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

        def get_project_versions(self, project_key, start_at=0, max_results=50):
            params = {"startAt": start_at, "maxResults": max_results}
            resp = requests.get(
                f"{self.base_url}/rest/api/3/project/{project_key}/versions",
                params=params,
            )
            return resp.json()

        def find_boards(self, project_key=None):
            params = {}
            if project_key:
                params["projectKeyOrId"] = project_key
            resp = requests.get(f"{self.base_url}/rest/agile/1.0/board", params=params)
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


def versions_payload(project_key: str, count: int = 2) -> Dict[str, Any]:
    return [
        {
            "id": str(200 + i),
            "name": f"v{i+1}",
            "description": "",
            "released": False,
        }
        for i in range(count)
    ]


def boards_payload(project_key: str) -> Dict[str, Any]:
    return {
        "maxResults": 50,
        "startAt": 0,
        "total": 1,
        "values": [
            {"id": 11, "name": f"{project_key} Board", "type": "scrum", "location": {}}
        ],
    }
