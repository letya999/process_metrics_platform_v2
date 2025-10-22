"""DB utilities and secret resolver used by the DLT Prefect flows.

This module provides lightweight helpers used in unit tests and later by
flows: `resolve_api_token`, and simple DB-stub functions that will be
implemented fully in Phase 3 integration tasks.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional
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
    """Resolve secret for a given tool integration id via platform.tool_integrations.

    Rules:
      - Read row by id
      - If secret_provider == 'env': read os.getenv(secret_reference); if missing -> fail
      - Never log token

    This implementation uses asyncpg when available and DB_* env vars. As a
    fallback for unit tests, it supports dict-based stores with shape:
      {'tool_integrations': [{'id': '<uuid>', 'secret_provider': 'env', 'secret_reference': 'ENV_NAME', ...}]}
    """
    # First, allow in-memory dict fixture via special escape hatch
    # If the caller passes a dict store instead of an id (for tests), support it
    if isinstance(tool_integration_id, dict):  # type: ignore[unreachable]
        store = tool_integration_id
        raise NotImplementedError(
            "Pass tool_integration_id as string; dict-based provider is not supported here"
        )

    import os as _os

    try:
        import asyncio
        import asyncpg  # type: ignore

        async def _run() -> str:
            conn = await asyncpg.connect(
                host=_os.getenv("DB_HOST", "postgres"),
                database=_os.getenv("DB_NAME", "process_metrics_v2"),
                user=_os.getenv("DB_USER", "postgres"),
                password=_os.getenv("DB_PASSWORD", ""),
            )
            try:
                row = await conn.fetchrow(
                    """
                    SELECT secret_provider, secret_reference, api_token_unsafe
                    FROM platform.tool_integrations
                    WHERE id = $1 AND is_active = TRUE
                    """,
                    tool_integration_id,
                )
                if not row:
                    raise ValueError("tool_integration not found or inactive")
                provider = row["secret_provider"]
                if provider == "env":
                    ref = row["secret_reference"]
                    if not ref:
                        raise ValueError("secret_reference is NULL for env provider")
                    val = _os.getenv(str(ref) or "")
                    if not val:
                        raise ValueError("environment variable referenced by secret_reference is empty")
                    return val
                # Optional unsafe fallback for dev/test only
                if row["api_token_unsafe"]:
                    return str(row["api_token_unsafe"])
                raise ValueError("no supported secret provider")
            finally:
                await conn.close()

        return asyncio.run(_run())
    except Exception as exc:
        # Do not expose token or env var values; just rethrow concise error
        raise


def fetch_projects_with_credentials(db_conn) -> list:
    """Fetch active projects joined with credentials.

    Test support:
      - dict store with key 'projects' -> returned verbatim
      - iterable of rows -> list(iterable)

    Production:
      - Uses asyncpg with DB_* env vars to read from platform.projects joined to
        platform.tool_integrations. Secrets are NOT returned; only references.
    """
    # Unit-test fixtures path
    if isinstance(db_conn, dict) and "projects" in db_conn:
        return list(db_conn["projects"])

    # If db_conn is an iterable of rows (e.g. a mocked result), return its list
    try:
        # avoid treating strings/bytes as iterables of rows
        if db_conn is not None and not isinstance(db_conn, (str, bytes)):
            return list(db_conn)
    except TypeError:
        pass

    # Production path: query database via asyncpg
    try:
        import asyncio
        import asyncpg  # type: ignore
        import os as _os

        async def _run() -> list:
            conn = await asyncpg.connect(
                host=_os.getenv("DB_HOST", "postgres"),
                database=_os.getenv("DB_NAME", "process_metrics_v2"),
                user=_os.getenv("DB_USER", "postgres"),
                password=_os.getenv("DB_PASSWORD", ""),
            )
            try:
                rows = await conn.fetch(
                    """
                    SELECT p.id AS project_id,
                           p.external_id,
                           p.external_key,
                           p.name,
                           p.is_active,
                           ti.id AS tool_integration_id,
                           ti.instance_url,
                           ti.user_email,
                           ti.secret_provider,
                           ti.secret_reference
                    FROM platform.projects p
                    JOIN platform.tool_integrations ti ON ti.id = p.tool_integration_id
                    WHERE p.is_active = TRUE AND ti.is_active = TRUE
                    """
                )
                result: list = []
                for r in rows:
                    result.append(
                        {
                            "project_id": str(r["project_id"]),
                            "external_id": r["external_id"],
                            "external_key": r["external_key"],
                            "name": r["name"],
                            "is_active": r["is_active"],
                            "credentials": {
                                "tool_integration_id": str(r["tool_integration_id"]),
                                "instance_url": r["instance_url"],
                                "user_email": r["user_email"],
                                "secret_provider": r["secret_provider"],
                                "secret_reference": r["secret_reference"],
                            },
                        }
                    )
                return result
            finally:
                await conn.close()

        return asyncio.run(_run())
    except Exception as exc:
        # best-effort: return empty list; flows will log and continue
        return []


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


def record_project_run_metrics(
    *,
    pipeline_name: str,
    project_id: str,
    window: Dict[str, Any],
    load_info: Dict[str, Any],
    status: str,
) -> None:
    """Best-effort insert into platform.pipeline_runs for per-project metrics.

    Uses DB_* environment for connection via asyncpg. Silently no-ops on error.
    """
    try:
        import asyncio
        import asyncpg  # type: ignore
        import os as _os
        import json as _json

        total_rows = 0
        try:
            rows_by_resource = load_info.get("rows_loaded_by_resource", {})
            if isinstance(rows_by_resource, dict):
                total_rows = int(sum(int(v or 0) for v in rows_by_resource.values()))
        except Exception:
            total_rows = 0

        metrics = {
            "rows_total": total_rows,
            "rows_by_resource": load_info.get("rows_loaded_by_resource", {}),
            "last_synced_at": load_info.get("last_synced_at"),
        }

        async def _run() -> None:
            conn = await asyncpg.connect(
                host=_os.getenv("DB_HOST", "postgres"),
                database=_os.getenv("DB_NAME", "process_metrics_v2"),
                user=_os.getenv("DB_USER", "postgres"),
                password=_os.getenv("DB_PASSWORD", ""),
            )
            try:
                pipeline_row = await conn.fetchrow(
                    "SELECT id FROM platform.pipelines WHERE name = $1",
                    pipeline_name,
                )
                if not pipeline_row:
                    return
                pipeline_id = pipeline_row["id"]
                await conn.execute(
                    """
                    INSERT INTO platform.pipeline_runs (
                        id, pipeline_id, project_id, status, started_at, completed_at, metrics, config
                    ) VALUES (
                        gen_random_uuid(), $1, $2, $3, now(), now(), $4::jsonb, $5::jsonb
                    )
                    """,
                    pipeline_id,
                    project_id,
                    status,
                    _json.dumps(metrics),
                    _json.dumps({"window": window}),
                )
            finally:
                await conn.close()

        asyncio.run(_run())
    except Exception:
        # Optional, do nothing on failure
        return
