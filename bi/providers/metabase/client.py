from __future__ import annotations

import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)


class MetabaseClient:
    def __init__(self, base_url: str, timeout: int = 20):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._headers: dict[str, str] = {"Content-Type": "application/json"}

    @property
    def headers(self) -> dict[str, str]:
        return self._headers

    def with_api_key(self, api_key: str) -> None:
        self._headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
        }

    def with_session(self, session_id: str) -> None:
        self._headers = {
            "Content-Type": "application/json",
            "X-Metabase-Session": session_id,
        }

    def wait_for_health(self, max_wait_seconds: int = 300) -> None:
        deadline = time.time() + max_wait_seconds
        health_url = f"{self.base_url}/api/health"

        while time.time() < deadline:
            try:
                response = requests.get(health_url, timeout=5)
                if response.status_code == 200:
                    logger.info("Metabase is healthy")
                    return
            except requests.RequestException:
                pass
            time.sleep(3)

        raise RuntimeError("Metabase did not become healthy in time")

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | list[Any] | None = None,
        expected_statuses: tuple[int, ...] = (200,),
    ) -> Any:
        url = f"{self.base_url}{path}"
        response = requests.request(
            method=method,
            url=url,
            headers=self._headers,
            json=json_body,
            timeout=self.timeout,
        )

        if response.status_code not in expected_statuses:
            raise RuntimeError(
                f"Metabase API error {response.status_code} on {method} {path}: {response.text}"
            )

        if not response.content:
            return None

        try:
            return response.json()
        except ValueError:
            return response.text
