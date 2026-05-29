"""
Metric Registry: Centralized utility for resolving metadata IDs from the database.
Uses a simple dictionary cache with TTL within the process to minimize database queries.
"""

import threading
import time
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

# In-memory cache for the duration of the asset execution
# Format: {cache_key: {"value": any, "expires_at": float}}
_CACHE: Dict[str, Dict[str, Any]] = {}
_TTL = 300  # 5 minutes
_CACHE_LOCK = threading.Lock()


def _get_from_cache(key: str) -> Optional[Any]:
    """Get value from cache if it exists and hasn't expired."""
    with _CACHE_LOCK:
        entry = _CACHE.get(key)
        if entry and entry["expires_at"] > time.time():
            return entry["value"]
    return None


def _set_in_cache(key: str, value: Any) -> None:
    """Store value in cache with expiration."""
    with _CACHE_LOCK:
        _CACHE[key] = {"value": value, "expires_at": time.time() + _TTL}


def get_calculation_id(engine: Engine, calc_code: str) -> str:
    """Return UUID of calculations row by calc_code. Raise if not found."""
    cache_key = f"calc_id_{calc_code}"
    val = _get_from_cache(cache_key)
    if val is not None:
        return val

    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT id FROM metrics.calculations WHERE calc_code = :calc_code"),
            {"calc_code": calc_code},
        ).scalar()

    if not result:
        raise ValueError(
            f"Calculation code '{calc_code}' not found in metrics.calculations."
        )

    _set_in_cache(cache_key, str(result))
    return str(result)


def get_definition_id(engine: Engine, metric_code: str) -> str:
    """Return UUID of definitions row by metric_code."""
    cache_key = f"def_id_{metric_code}"
    val = _get_from_cache(cache_key)
    if val is not None:
        return val

    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT id FROM metrics.definitions WHERE metric_code = :metric_code"),
            {"metric_code": metric_code},
        ).scalar()

    if not result:
        raise ValueError(
            f"Metric code '{metric_code}' not found in metrics.definitions."
        )

    _set_in_cache(cache_key, str(result))
    return str(result)


def get_project_agg_id(engine: Engine, project_id: str) -> str:
    """Return dim_projects.id for given clean_jira project_id."""
    cache_key = f"proj_agg_id_{project_id}"
    val = _get_from_cache(cache_key)
    if val is not None:
        return val

    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT id FROM metrics.dim_projects WHERE project_id = :project_id"),
            {"project_id": project_id},
        ).scalar()

    if not result:
        _sync_dim_projects(engine)
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT id FROM metrics.dim_projects WHERE project_id = :project_id"
                ),
                {"project_id": project_id},
            ).scalar()
        if not result:
            raise ValueError(
                f"Project ID '{project_id}' not found in metrics.dim_projects. Run sync_dim_projects."
            )

    _set_in_cache(cache_key, str(result))
    return str(result)


def get_project_agg_ids_batch(engine: Engine, project_ids: List[str]) -> Dict[str, str]:
    """Return {project_id: project_agg_id} for all given project_ids in one query."""
    result = {}
    missing = []
    for pid in project_ids:
        cached = _get_from_cache(f"proj_agg_id_{pid}")
        if cached is not None:
            result[pid] = cached
        else:
            missing.append(pid)

    if missing:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT project_id, id FROM metrics.dim_projects WHERE project_id = ANY(CAST(:ids AS uuid[]))"
                ),
                {"ids": missing},
            ).fetchall()
        for row in rows:
            pid, agg_id = str(row[0]), str(row[1])
            _set_in_cache(f"proj_agg_id_{pid}", agg_id)
            result[pid] = agg_id

        for pid in missing:
            if pid not in result:
                _sync_dim_projects(engine)
                with engine.connect() as conn:
                    retry_rows = conn.execute(
                        text(
                            "SELECT project_id, id FROM metrics.dim_projects WHERE project_id = ANY(CAST(:ids AS uuid[]))"
                        ),
                        {"ids": missing},
                    ).fetchall()
                for row in retry_rows:
                    retry_pid, agg_id = str(row[0]), str(row[1])
                    _set_in_cache(f"proj_agg_id_{retry_pid}", agg_id)
                    result[retry_pid] = agg_id
                break

        for pid in missing:
            if pid not in result:
                raise ValueError(
                    f"Project ID '{pid}' not found in metrics.dim_projects."
                )

    return result


def resolve_unit_field(
    engine: Engine, project_id: str, unit_code: str
) -> Optional[Dict[str, Any]]:
    """
    Return {'source_field_id': uuid, 'source_entity': str} for given project/unit_code.
    Falls back to global (project_id=NULL) rule.
    Returns None if no config found or if specific source field isn't set.
    """
    cache_key = f"unit_{id(engine)}_{project_id}_{unit_code}"
    val = _get_from_cache(cache_key)
    if val is not None:
        return val

    with engine.connect() as conn:
        # Priority: specific project, then global NULL
        result = conn.execute(
            text("""
                SELECT source_field_id, source_entity, project_id
                FROM metrics.units
                WHERE unit_code = :unit_code
                  AND (project_id = :project_id OR project_id IS NULL)
                ORDER BY project_id NULLS LAST
                LIMIT 1
            """),
            {"unit_code": unit_code, "project_id": project_id},
        ).fetchone()

    if not result or not result[0]:
        _set_in_cache(cache_key, None)
        return None

    val = {"source_field_id": str(result[0]), "source_entity": result[1]}
    _set_in_cache(cache_key, val)
    return val


def clear_cache():
    """Clear the internal cache (useful for tests)."""
    with _CACHE_LOCK:
        _CACHE.clear()


def _sync_dim_projects(engine: Engine) -> None:
    """Backfill metrics.dim_projects from clean_jira.projects."""
    with engine.begin() as conn:
        conn.execute(text("""
                INSERT INTO metrics.dim_projects (project_id, project_key)
                SELECT id, external_key FROM clean_jira.projects
                ON CONFLICT (project_id) DO UPDATE
                SET project_key = EXCLUDED.project_key
                """))
