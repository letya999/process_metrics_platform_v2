"""HTTP client for Jira Cloud used by DLT source.

This module isolates network code so it can be unit-tested separately from
DLT resource wiring.
"""

# ruff: noqa: E501
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, Optional

from dlt.sources.helpers import requests

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
        self.session.headers.update(
            {"Accept": "application/json", "Content-Type": "application/json"}
        )
        # headers already set above; avoid printing token/secret in normal runs

    def _get(
        self, path: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        url = f"{self.instance_url}/{path.lstrip('/')}"
        max_retries = int(os.getenv("JIRA_API_RETRIES", "3"))
        backoff = float(os.getenv("JIRA_API_BACKOFF", "0.5"))
        for attempt in range(1, max_retries + 1):
            try:
                resp = self.session.get(
                    url, params=params, timeout=JIRA_API_TIMEOUT_SECONDS
                )
            except Exception as exc:
                if attempt == max_retries:
                    raise JiraHTTPError(f"GET {url} -> network error: {exc}") from exc
                time.sleep(backoff * attempt)
                continue
            if resp.status_code >= 500 and attempt < max_retries:
                time.sleep(backoff * attempt)
                continue
            if resp.status_code >= 400:
                raise JiraHTTPError(f"GET {url} -> {resp.status_code}: {resp.text}")
            try:
                return resp.json()
            except Exception as exc:
                raise JiraHTTPError(
                    f"GET {url} -> invalid json response: {exc}"
                ) from exc

    def _post(
        self,
        path: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{self.instance_url}/{path.lstrip('/')}"

        # Логирование для отладки минимально
        print("DEBUG: _post() called", file=sys.stderr)
        print(f"  URL: {url}", file=sys.stderr)
        print(f"  Headers: {dict(self.session.headers)}", file=sys.stderr)
        try:
            # Avoid extremely long single-line prints; dump separately for readability
            payload_str = json.dumps(json_data, indent=2, default=str)
            print("  payload:", file=sys.stderr)
            print(payload_str, file=sys.stderr)
        except Exception:
            print(f"  payload: {json_data}", file=sys.stderr)
        max_retries = int(os.getenv("JIRA_API_RETRIES", "3"))
        backoff = float(os.getenv("JIRA_API_BACKOFF", "0.5"))
        for attempt in range(1, max_retries + 1):
            try:
                resp = self.session.post(
                    url,
                    json=json_data,
                    params=params,
                    timeout=JIRA_API_TIMEOUT_SECONDS,
                )
            except Exception as exc:
                if attempt == max_retries:
                    raise JiraHTTPError(f"POST {url} -> network error: {exc}") from exc
                time.sleep(backoff * attempt)
                continue
            if resp.status_code >= 500 and attempt < max_retries:
                time.sleep(backoff * attempt)
                continue
            if resp.status_code >= 400:
                try:
                    error_body = resp.json()
                except Exception:
                    error_body = resp.text
                print("DEBUG: Response error:", file=sys.stderr)
                print(f"  status_code: {resp.status_code}", file=sys.stderr)
                print(f"  error_body: {error_body}", file=sys.stderr)
                raise JiraHTTPError(f"POST {url} -> {resp.status_code}: {error_body}")
            try:
                return resp.json()
            except Exception as exc:
                raise JiraHTTPError(
                    f"POST {url} -> invalid json response: {exc}"
                ) from exc

    def search_issues(
        self,
        jql: str,
        start_at: int = 0,
        max_results: int = 100,
        fields: Optional[list] = None,
    ) -> Dict[str, Any]:
        """Use the POST `/rest/api/3/search/jql` endpoint that replaced the old GET /search.

        Keeps backward-compatible `start_at` by including `startAt` when non-zero.
        """
        print("=== search_issues() called ===", file=sys.stderr)
        print(f"  jql: {jql}", file=sys.stderr)
        print(f"  start_at: {start_at}", file=sys.stderr)
        print(f"  max_results: {max_results}", file=sys.stderr)
        print(f"  fields: {fields}", file=sys.stderr)

        # JSON payload for POST body - include jql, maxResults and optional fields (as array)
        # Do NOT include startAt when it's 0; add it only for subsequent pages (matches run_dlt_import.py)
        payload: Dict[str, Any] = {"jql": jql, "maxResults": int(max_results)}
        if fields:
            payload["fields"] = (
                fields
                if isinstance(fields, list)
                else [f.strip() for f in str(fields).split(",") if f.strip()]
            )

        # Add startAt only when non-zero (first request should omit it)
        if int(start_at) > 0:
            payload["startAt"] = int(start_at)

        # Primary: call the JQL-specific endpoint with fields in the JSON body and pagination in body
        try:
            try:
                final_payload_str = json.dumps(payload, indent=2, default=str)
                print("  Final payload:", file=sys.stderr)
                print(final_payload_str, file=sys.stderr)
            except Exception:
                print(f"  Final payload: {payload}", file=sys.stderr)
            return self._post("/rest/api/3/search/jql", json_data=payload)
        except JiraHTTPError as e:
            raise JiraHTTPError(f"search_issues jql={jql} -> {e}")

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
