"""DB utilities and secret resolver used by the DLT Prefect flows.

This module provides lightweight helpers used in unit tests and later by
flows: `resolve_api_token`, and simple DB-stub functions that will be
implemented fully in Phase 3 integration tasks.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import asyncio
from uuid import uuid4


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


def resolve_integration_secret(tool_integration_id: str) -> str:
    """Resolve secret for a tool integration strictly via env provider.

    Contract:
    - Read platform.tool_integrations row by id (placeholder here);
    - If secret_provider == 'env', use secret_reference as env var name;
    - Never log or persist the token; raise if missing.

    Note: This version is a scaffold: when real DB access is added, implement
    an asyncpg query to fetch the row. For now, we accept an override via
    environment variable name pattern `INTEGRATION_SECRET_REF_<ID>` that
    points to the actual env var holding the token. This avoids embedding
    secrets in tests and keeps behavior deterministic.
    """
    # 1) Determine env var that contains the secret reference
    # Example: INTEGRATION_SECRET_REF_<uuid> = JIRA_API_TOKEN__ACME
    ref_env = f"INTEGRATION_SECRET_REF_{tool_integration_id}"
    secret_ref = os.getenv(ref_env)
    if not secret_ref:
        # As a convenience for local/dev, allow direct var name convention
        # TOKEN_<id> to be the actual token (not recommended). Only used in tests.
        direct = os.getenv(f"TOKEN_{tool_integration_id}")
        if direct:
            return direct
        raise ValueError("Missing secret reference for integration")

    token = os.getenv(secret_ref)
    if not token:
        raise ValueError("Secret reference present but token env is empty")
    return token


async def _upsert_pipeline_prefect_ids_async(
    *, pipeline_name: str, prefect_flow_id: Optional[str], prefect_deployment_id: Optional[str]
) -> None:
    """Async upsert using asyncpg; silently no-ops if asyncpg unavailable."""
    try:
        import asyncpg  # type: ignore
    except Exception:
        return

    db_host = os.getenv("DB_HOST", "postgres")
    db_name = os.getenv("DB_NAME") or os.getenv("POSTGRES_DB")
    db_user = os.getenv("DB_USER") or os.getenv("POSTGRES_USER")
    db_pass = os.getenv("DB_PASSWORD") or os.getenv("POSTGRES_PASSWORD")
    db_port = int(os.getenv("DB_PORT", "5432"))

    if not (db_name and db_user and db_pass):
        return

    conn = await asyncpg.connect(
        user=db_user, password=db_pass, database=db_name, host=db_host, port=db_port
    )
    try:
        # Ensure pipeline row exists and update IDs
        await conn.execute(
            """
            INSERT INTO platform.pipelines (name, description, is_active, prefect_flow_id, prefect_deployment_id)
            VALUES ($1, 'Jira Cloud data synchronization pipeline (Prefect + DLT)', TRUE, $2, $3)
            ON CONFLICT (name) DO UPDATE SET
                prefect_flow_id = EXCLUDED.prefect_flow_id,
                prefect_deployment_id = EXCLUDED.prefect_deployment_id,
                updated_at = now();
            """,
            pipeline_name,
            prefect_flow_id,
            prefect_deployment_id,
        )
    finally:
        await conn.close()


def upsert_pipeline_prefect_ids(
    *, pipeline_name: str, prefect_flow_id: Optional[str], prefect_deployment_id: Optional[str]
) -> None:
    """Best-effort upsert of Prefect IDs into platform.pipelines using asyncpg."""
    try:
        asyncio.run(
            _upsert_pipeline_prefect_ids_async(
                pipeline_name=pipeline_name,
                prefect_flow_id=prefect_flow_id,
                prefect_deployment_id=prefect_deployment_id,
            )
        )
    except Exception:
        # Silent best-effort; do not fail init on DB errors
        pass


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


# -----------------------------
# Pipeline run tracking (in-memory helpers)
# -----------------------------


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    )


def ensure_pipeline(db_conn: Dict[str, Any], name: str) -> str:
    """Ensure a pipeline entry exists in the in-memory store and return its id.

    The in-memory shape mirrors a minimal subset of platform.pipelines:
    db_conn = { 'pipelines': [{'id': '...', 'name': 'jira_sync', ...}], ... }
    """
    if not isinstance(db_conn, dict):
        raise NotImplementedError(
            "ensure_pipeline requires dict-based db_conn for tests"
        )

    pipelines = db_conn.setdefault("pipelines", [])
    for p in pipelines:
        if p.get("name") == name:
            return p["id"]

    pid = str(uuid4())
    pipelines.append(
        {"id": pid, "name": name, "created_at": _now_iso(), "is_active": True}
    )
    return pid


def create_pipeline_run(
    db_conn: Dict[str, Any],
    *,
    pipeline_name: str,
    config: Optional[Dict[str, Any]] = None,
) -> str:
    """Create an in-memory pipeline_run row and return its id."""
    if not isinstance(db_conn, dict):
        raise NotImplementedError(
            "create_pipeline_run requires dict-based db_conn for tests"
        )

    pipeline_id = ensure_pipeline(db_conn, pipeline_name)
    run_id = str(uuid4())
    runs = db_conn.setdefault("pipeline_runs", [])
    runs.append(
        {
            "id": run_id,
            "pipeline_id": pipeline_id,
            "status": "running",
            "started_at": _now_iso(),
            "config": dict(config or {}),
        }
    )
    return run_id


def finalize_pipeline_run(
    db_conn: Dict[str, Any],
    run_id: str,
    *,
    status: str,
    metrics: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None,
) -> Dict[str, Any]:
    """Finalize a pipeline run: set status, completed_at, metrics, and duration."""
    if not isinstance(db_conn, dict):
        raise NotImplementedError(
            "finalize_pipeline_run requires dict-based db_conn for tests"
        )

    runs = db_conn.setdefault("pipeline_runs", [])
    for r in runs:
        if r.get("id") == run_id:
            r["status"] = status
            r["completed_at"] = _now_iso()
            if metrics is not None:
                r["metrics"] = metrics
            if error_message:
                r["error_message"] = error_message
            # best-effort duration calculation if started_at exists
            try:
                if r.get("started_at") and r.get("completed_at"):
                    start_dt = datetime.fromisoformat(
                        r["started_at"].replace("Z", "+00:00")
                    )
                    end_dt = datetime.fromisoformat(
                        r["completed_at"].replace("Z", "+00:00")
                    )
                    r["duration_seconds"] = int((end_dt - start_dt).total_seconds())
            except Exception:
                pass
            return r

    raise KeyError(f"pipeline run id not found: {run_id}")
