#!/usr/bin/env python3
"""Run DLT for Jira projects using credentials fetched from the platform DB.

Usage:
  - Run for a single project key:
      python run_dlt_from_db.py --project PROJKEY
  - Run for all active projects:
      python run_dlt_from_db.py --all

This script connects to Postgres (uses env var DATABASE_URL or POSTGRES_* vars),
reads active projects joined with their tool_integration row, resolves tokens
from env or fallback, then invokes the DLT source and runs `dlt.run(...)`.

Run inside the service image (recommended):
  docker build -t dlt_jira_loader_local ./services/dlt_jira_loader
  docker run --rm --env-file .env --network process_metrics_network dlt_jira_loader_local \
    python /app/services/dlt_jira_loader/scripts/run_dlt_from_db.py --all

Or run locally in project's venv with env vars set.
"""
# ruff: noqa: E501
from __future__ import annotations

import argparse
import asyncio
import os
import re
from typing import Any, Dict, List
from urllib.parse import unquote, urlparse

import asyncpg
import dlt

from services.dlt_jira_loader.app.dlt_sources.jira_cloud import jira_source

DEFAULT_DB_PORT = 5432


def build_db_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        # Support SQLAlchemy-style DSNs in .env (e.g. postgresql+asyncpg://...)
        # asyncpg expects scheme 'postgresql' or 'postgres' so strip any +driver suffix.
        # Use regex to replace 'postgresql+<driver>://' with 'postgresql://'.
        sanitized = re.sub(r"^(postgresql)\+[^:]+:\/\/", r"\1://", url)
        return sanitized
    user = os.getenv("POSTGRES_USER", "postgres")
    pw = os.getenv("POSTGRES_PASSWORD")
    db = os.getenv("POSTGRES_DB", "process_metrics_v2")
    host = os.getenv("POSTGRES_HOST", os.getenv("POSTGRES_HOSTNAME", "postgres"))
    port = os.getenv("POSTGRES_PORT", str(DEFAULT_DB_PORT))
    if not pw:
        raise RuntimeError("POSTGRES_PASSWORD or DATABASE_URL must be set in env")
    return f"postgresql://{user}:{pw}@{host}:{port}/{db}"


def create_pipeline(pipeline_name: str, dataset_name: str, db_url_env: str):
    """Create and configure a dlt pipeline without persisting secrets to disk.

    This helper sets minimal env vars (only if not present) and stores the
    destination password in dlt.secrets in-memory. It avoids writing any
    configuration files to the workspace.
    """
    if db_url_env:
        p = urlparse(db_url_env)
        db_user = unquote(p.username) if p.username else ""
        db_password = unquote(p.password) if p.password else ""
        db_host = p.hostname or "postgres"
        _db_port = p.port or 5432
        db_name = p.path.lstrip("/") if p.path else ""

        # Export non-secret config pieces as env-vars only if not already set
        os.environ.setdefault("DESTINATION__POSTGRES__CREDENTIALS__HOST", str(db_host))
        os.environ.setdefault(
            "DESTINATION__POSTGRES__CREDENTIALS__USERNAME", str(db_user)
        )
        os.environ.setdefault(
            "DESTINATION__POSTGRES__CREDENTIALS__DATABASE", str(db_name)
        )

        pipeline_env_prefix = pipeline_name.upper()
        os.environ.setdefault(
            f"{pipeline_env_prefix}__DESTINATION__POSTGRES__CREDENTIALS__HOST",
            str(db_host),
        )
        os.environ.setdefault(
            f"{pipeline_env_prefix}__DESTINATION__POSTGRES__CREDENTIALS__USERNAME",
            str(db_user),
        )
        os.environ.setdefault(
            f"{pipeline_env_prefix}__DESTINATION__POSTGRES__CREDENTIALS__DATABASE",
            str(db_name),
        )

        # Set password in dlt.secrets (in-memory) only when provided; do not write files.
        try:
            if db_password:
                key1 = f"{pipeline_name}.destination.postgres.credentials.password"
                key2 = "destination.postgres.credentials.password"
                if not dlt.secrets.get(key1):
                    dlt.secrets[key1] = db_password
                if not dlt.secrets.get(key2):
                    dlt.secrets[key2] = db_password
        except Exception:
            # Last-resort: fallback to env (still avoid writing files)
            if db_password:
                os.environ.setdefault(
                    "DESTINATION__POSTGRES__CREDENTIALS__PASSWORD", str(db_password)
                )
                os.environ.setdefault(
                    f"{pipeline_env_prefix}__DESTINATION__POSTGRES__CREDENTIALS__PASSWORD",
                    str(db_password),
                )

    pipeline = dlt.pipeline(
        pipeline_name=pipeline_name, destination="postgres", dataset_name=dataset_name
    )
    return pipeline


async def fetch_projects(
    conn: asyncpg.Connection, project_key: str | None = None
) -> List[Dict[str, Any]]:
    q = """
    SELECT p.external_key, p.external_id, p.name,
           ti.instance_url, ti.user_email, ti.secret_provider, ti.secret_reference, ti.api_token_unsafe
    FROM platform.projects p
    JOIN platform.tool_integrations ti ON p.tool_integration_id = ti.id
    WHERE p.is_active = true
    """
    if project_key:
        q += " AND p.external_key = $1"
        rows = await conn.fetch(q, project_key)
    else:
        rows = await conn.fetch(q)

    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "external_key": r["external_key"],
                "external_id": r["external_id"],
                "name": r["name"],
                "instance_url": r["instance_url"],
                "user_email": r["user_email"],
                "secret_provider": r["secret_provider"],
                "secret_reference": r["secret_reference"],
                "api_token_unsafe": r["api_token_unsafe"],
            }
        )
    return out


def resolve_token(row: Dict[str, Any]) -> str | None:
    provider = row.get("secret_provider")
    if provider == "env":
        ref = row.get("secret_reference")
        if ref:
            # primary: resolve from environment variable name stored in secret_reference
            val = os.getenv(ref)
            if val:
                return val
            # fallback: some rows may mistakenly store the literal token in secret_reference
            # (instead of the env var name). If it looks like a token, accept it.
            if isinstance(ref, str) and len(ref) > 20:
                print(
                    "[warning] secret_reference appears to contain a literal token; using it for this run"
                )
                return ref
    # fallback
    return row.get("api_token_unsafe")


def run_for_project(project: Dict[str, Any], dataset_name: str) -> None:
    project_key = project["external_key"]
    instance_url = project.get("instance_url")
    user_email = project.get("user_email")
    token = resolve_token(project)

    if not token:
        print(
            f"[skipping] project {project_key}: no API token available (check secret_reference or api_token_unsafe)"
        )
        return

    cfg = {"instance_url": instance_url, "user_email": user_email, "api_token": token}
    print(f"Running DLT for {project_key} -> dataset {dataset_name}")
    issues_res, sprints_res, comments_res, releases_res, boards_res = jira_source(
        project_key, cfg
    )

    # Build resource callables (do NOT call them). Use wrappers to pre-bind args
    # while preserving function metadata so DLT can infer resource names.

    resource_callables = []

    # issues (no args)
    resource_callables.append(issues_res)

    # releases (bind project_key) using dlt resource binding
    try:
        resource_callables.append(releases_res.bind(project_key=project_key))
    except Exception:
        resource_callables.append(releases_res)

    # boards (no args)
    resource_callables.append(boards_res)

    # sprints: create one resource callable per board that binds board_id
    try:
        boards_list = list(boards_res())
        board_ids = [
            b.get("board_id")
            for b in boards_list
            if isinstance(b, dict) and b.get("board_id")
        ]
        for bid in board_ids:
            try:
                resource_callables.append(sprints_res.bind(board_id=bid))
            except Exception:
                # fallback to unbound if bind not supported
                resource_callables.append(sprints_res)
    except Exception:
        # fallback: include sprints_res unbound
        resource_callables.append(sprints_res)

    # comments resource (may require issue_key but safe to include unbound)
    resource_callables.append(comments_res)

    # run DLT
    # Create a dlt pipeline (ensures destination is provided) and run using a small
    # dlt.source wrapper that returns our instantiated resources. This mirrors
    # the working example script `run_dlt_import.py`.
    try:
        db_url_env = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or ""
        pipeline_name = f"jira_manual_{project_key}"
        pipeline = create_pipeline(
            pipeline_name=pipeline_name,
            dataset_name=dataset_name,
            db_url_env=db_url_env,
        )

        @dlt.source
        def _manual_source():
            # Return resource callables for dlt to consume
            return tuple(resource_callables)

        result = pipeline.run(_manual_source)
        print("DLT run result:", result)
    except Exception as e:
        print(f"DLT run failed for project {project_key}: {e}")


async def main_async(args: argparse.Namespace) -> None:
    db_url = build_db_url()

    # Ensure DLT has a destination configured. Try a few common env var names so
    # different dlt versions/configurations will pick it up.
    sanitized_db = db_url
    os.environ.setdefault("DLT_DESTINATION", "postgres")
    os.environ.setdefault("DLT_POSTGRES__CONNECTION_STRING", sanitized_db)
    os.environ.setdefault("DLT_POSTGRES__CONNECTION_URI", sanitized_db)
    os.environ.setdefault("DLT_POSTGRES__URI", sanitized_db)
    # also set common fallbacks
    os.environ.setdefault("POSTGRES_URI", sanitized_db)
    os.environ.setdefault("DATABASE_URL", sanitized_db)

    print(f"[info] using DB for asyncpg and DLT: {sanitized_db}")

    conn = await asyncpg.connect(dsn=db_url)
    try:
        projects = await fetch_projects(
            conn, project_key=(args.project if not args.all else None)
        )
        if not projects:
            print("No active projects found to run; exiting")
            return

        if args.project and len(projects) == 0:
            print(f"Project {args.project} not found or inactive")
            return

        # Ensure real runs are enabled
        if os.getenv("DLT_ENABLE_REAL_RUN", "0") not in ("1", "true", "True"):
            print(
                "WARNING: DLT_ENABLE_REAL_RUN is not set to 1 — dlt may do dry-run or skip writes"
            )

        for p in projects:
            run_for_project(p, args.dataset)

    finally:
        await conn.close()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument("--project", help="Single Jira project key to run (external_key)")
    grp.add_argument("--all", action="store_true", help="Run for all active projects")
    p.add_argument(
        "--dataset", default="raw_jira_cloud_dlt", help="DLT dataset name to write to"
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
