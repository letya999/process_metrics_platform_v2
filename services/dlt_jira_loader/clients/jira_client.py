"""HTTP client for Jira Cloud used by DLT source.

This module isolates network code so it can be unit-tested separately from
DLT resource wiring.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

import requests

JIRA_API_TIMEOUT_SECONDS = 30


class JiraHTTPError(Exception):
    """Raised when a Jira HTTP request returns a non-2xx response."""


class JiraClient:
    """Tiny Jira HTTP client used by the DLT source.

    Public methods:
      - search_issues(jql, start_at, max_results)
      - get_sprints(board_id, start_at, max_results)
      - get_comments(issue_key, start_at, max_results)
    """

    def __init__(self, instance_url: str, api_token: str, email: str) -> None:
        self.instance_url = instance_url.rstrip("/")
        self.api_token = api_token
        self.email = email
        self.session = requests.Session()
        self.session.auth = (self.email, self.api_token)
        self.session.headers.update({"Accept": "application/json"})

    def _get(
        self, path: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        url = f"{self.instance_url}/{path.lstrip('/')}"
        resp = self.session.get(url, params=params, timeout=JIRA_API_TIMEOUT_SECONDS)
        if resp.status_code >= 400:
            raise JiraHTTPError(f"GET {url} -> {resp.status_code}: {resp.text}")
        return resp.json()

    def search_issues(
        self, jql: str, start_at: int = 0, max_results: int = 50
    ) -> Dict[str, Any]:
        return self._get(
            "/rest/api/3/search",
            params={"jql": jql, "startAt": start_at, "maxResults": max_results},
        )

    def get_sprints(
        self, board_id: int, start_at: int = 0, max_results: int = 50
    ) -> Dict[str, Any]:
        return self._get(
            f"/rest/agile/1.0/board/{board_id}/sprint",
            params={"startAt": start_at, "maxResults": max_results},
        )

    def get_project_versions(self, project_key: str) -> Dict[str, Any]:
        return self._get(f"/rest/api/3/project/{project_key}/versions")

    def find_boards(self, project_key: Optional[str] = None) -> Dict[str, Any]:
        params = {}
        if project_key:
            params["projectKeyOrId"] = project_key
        return self._get("/rest/agile/1.0/board", params=params)

    def get_comments(
        self, issue_key: str, start_at: int = 0, max_results: int = 50
    ) -> Dict[str, Any]:
        return self._get(
            f"/rest/api/3/issue/{issue_key}/comment",
            params={"startAt": start_at, "maxResults": max_results},
        )


def resolve_from_env_or_config(config: Dict[str, Any], key: str, env_key: str) -> str:
    """Resolve credential from config dict or environment variable.

    Raises ValueError if neither is present.
    """
    value = config.get(key) or os.getenv(env_key)
    if not value:
        raise ValueError(f"Missing credential: {key} or environment {env_key}")
    return value
