"""DB utilities and secret resolver used by the DLT Prefect flows.

This module provides lightweight helpers used in unit tests and later by
flows: `resolve_api_token`, and simple DB-stub functions that will be
implemented fully in Phase 3 integration tasks.
"""
from __future__ import annotations

import os
from typing import Any, Dict


def resolve_api_token(tool_integration_row: Dict[str, Any]) -> str:
    """Resolve API token from a DB row describing a tool integration.

    Order of resolution:
      1. `secret_provider` with provider `env` -> use `secret_reference` as env var name
      2. `api_token_unsafe` fallback

    Raises:
        ValueError if no token found.
    """
    # Preferred: explicit secret provider
    provider = tool_integration_row.get("secret_provider")
    if provider == "env":
        ref = tool_integration_row.get("secret_reference")
        if ref:
            val = os.getenv(ref)
            if val:
                return val

    # fallback: unsafe token stored in DB (only for tests/seeding)
    token = tool_integration_row.get("api_token_unsafe")
    if token:
        return token

    raise ValueError("No API token available for integration")


def fetch_projects_with_credentials(db_conn) -> list:
    """Placeholder: fetch active projects joined with credentials.

    For unit tests this can be mocked; real implementation will use asyncpg
    and proper SQL.
    """
    raise NotImplementedError


def upsert_sync_checkpoint(db_conn, checkpoint: Dict[str, Any]) -> None:
    """Placeholder for upserting integration_sync_checkpoints row."""
    raise NotImplementedError
