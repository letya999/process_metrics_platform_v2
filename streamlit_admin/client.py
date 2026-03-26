"""API client for Streamlit admin studio."""

import os
from typing import Any

import requests


class AdminApiClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = (
            base_url or os.getenv("ADMIN_API_URL") or "http://localhost:8000/api/v1"
        ).rstrip("/")

    def _headers(self, token: str | None = None) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def request(
        self, method: str, path: str, token: str | None = None, **kwargs: Any
    ) -> Any:
        resp = requests.request(
            method=method,
            url=f"{self.base_url}{path}",
            headers=self._headers(token),
            timeout=30,
            **kwargs,
        )
        if not resp.ok:
            raise RuntimeError(f"{resp.status_code}: {resp.text}")
        if resp.text:
            return resp.json()
        return None
