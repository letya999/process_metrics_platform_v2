"""DB utilities and secret resolver used by the DLT Prefect flows.

This module provides lightweight helpers used in unit tests and later by
flows: `resolve_api_token`, and simple DB-stub functions that will be
implemented fully in Phase 3 integration tasks.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
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
    # Support simple in-memory fixtures used by unit tests.
    # Supported inputs:
    # - None -> empty list
    # - dict with key 'projects' -> return that list
    # - iterable of project rows -> return list(iterable)
    if db_conn is None:
        return []

    if isinstance(db_conn, dict) and "projects" in db_conn:
        return list(db_conn["projects"])

    # If db_conn is an iterable of rows (e.g. a mocked result), return its list
    try:
        # avoid treating strings/bytes as iterables of rows
        if isinstance(db_conn, (str, bytes)):
            raise TypeError
        return list(db_conn)
    except TypeError:
        raise NotImplementedError(
            "fetch_projects_with_credentials: real DB connector not implemented; "
            "provide an iterable or dict{'projects': [...]} for tests"
        )


def upsert_sync_checkpoint(db_conn, checkpoint: Dict[str, Any]) -> None:
    """Placeholder for upserting integration_sync_checkpoints row."""
    # Support an in-memory dict-based store for unit tests.
    # Expected shape example:
    # db_conn = {
    #   'checkpoints': [
    #       {'tool_integration_id': ..., 'project_id': ..., 'entity_type': ..., ...},
    #   ]
    # }
    if db_conn is None:
        raise NotImplementedError(
            "upsert_sync_checkpoint: no db_conn provided; provide an in-memory dict "
            "for tests or implement DB logic"
        )

    if isinstance(db_conn, dict):
        cps = db_conn.setdefault("checkpoints", [])

        for idx, existing in enumerate(cps):
            if (
                existing.get("tool_integration_id")
                == checkpoint.get("tool_integration_id")
                and existing.get("project_id") == checkpoint.get("project_id")
                and existing.get("entity_type") == checkpoint.get("entity_type")
            ):
                updated = existing.copy()
                updated.update(checkpoint)
                updated["updated_at"] = (
                    datetime.now(timezone.utc)
                    .replace(microsecond=0)
                    .strftime("%Y-%m-%dT%H:%M:%SZ")
                )
                cps[idx] = updated
                return

        # insert new
        new_cp = checkpoint.copy()
        now = (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .strftime("%Y-%m-%dT%H:%M:%SZ")
        )
        new_cp.setdefault("created_at", now)
        new_cp.setdefault("updated_at", now)
        cps.append(new_cp)
        return

    raise NotImplementedError(
        "upsert_sync_checkpoint: only in-memory dict store "
        "is supported by this helper; "
        "implement DB upsert in integration phase"
    )
