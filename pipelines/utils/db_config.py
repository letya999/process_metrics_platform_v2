"""DB-driven project and integration configuration for Dagster pipelines.

Replaces config/projects.yaml as the source of truth for which projects
to sync and what credentials to use. Falls back to env vars if DB is
unavailable.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ProjectCredentials:
    project_key: str
    project_name: str
    integration_id: str
    instance_url: str
    user_email: str
    api_token: str


def _resolve_token(
    secret_provider: str | None,
    secret_reference: str | None,
    api_token_unsafe: str | None,
) -> str:
    """Resolve actual API token from storage strategy."""
    if secret_provider == "env" and secret_reference:  # noqa: S105
        token = os.getenv(secret_reference, "")
        if not token:
            logger.warning("Env var %s not set for integration token", secret_reference)
        return token
    if api_token_unsafe:
        return api_token_unsafe
    return ""


def get_active_projects_from_db() -> list[ProjectCredentials]:
    """Return credentials for all active projects from platform.projects + tool_integrations.

    Returns an empty list (with a warning) if the DB is unreachable or has no rows,
    so callers can fall back to env vars.
    """
    try:
        from pipelines.resources.database import _build_engine

        db_url = os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/process_metrics",
        )
        engine = _build_engine(db_url)

        query = """
            SELECT
                p.external_key,
                p.name,
                p.tool_integration_id::text,
                ti.instance_url,
                ti.user_email,
                ti.secret_provider,
                ti.secret_reference,
                ti.api_token_unsafe
            FROM platform.projects p
            JOIN platform.tool_integrations ti ON ti.id = p.tool_integration_id
            WHERE p.is_active = true
              AND ti.is_active = true
            ORDER BY p.created_at
        """
        with engine.connect() as conn:
            from sqlalchemy import text

            rows = conn.execute(text(query)).fetchall()

        result = []
        for row in rows:
            (
                key,
                name,
                integration_id,
                instance_url,
                user_email,
                secret_provider,
                secret_reference,
                api_token_unsafe,
            ) = row

            token = _resolve_token(secret_provider, secret_reference, api_token_unsafe)
            if not token:
                logger.warning("No token resolved for project %s, skipping", key)
                continue

            result.append(
                ProjectCredentials(
                    project_key=key,
                    project_name=name,
                    integration_id=integration_id,
                    instance_url=instance_url or "",
                    user_email=user_email or "",
                    api_token=token,
                )
            )

        logger.info("Loaded %d active projects from DB", len(result))
        return result

    except Exception as exc:
        logger.warning(
            "Cannot load projects from DB (%s), caller should fall back to env vars",
            exc,
        )
        return []


def get_project_credentials(project_key: str) -> ProjectCredentials | None:
    """Return credentials for a single project by key, or None if not found."""
    projects = get_active_projects_from_db()
    for p in projects:
        if p.project_key == project_key:
            return p
    return None
