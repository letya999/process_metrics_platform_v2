"""
Registry for resolving metric metadata from the database.
Provides caching and lookup functions for metric definitions, calculations, and projects.
"""

from typing import Dict, Optional

from sqlalchemy import Engine, text

from .polars_db import read_table

# In-memory cache
_cache: Dict[str, Dict] = {
    "calc_ids": {},
    "def_ids": {},
    "project_agg_ids": {},
}


def get_calculation_id(engine: Engine, calc_code: str) -> str:
    """Return UUID of calculations row by calc_code. Raise if not found."""
    if calc_code in _cache["calc_ids"]:
        return _cache["calc_ids"][calc_code]

    query = "SELECT id FROM metrics.calculations WHERE calc_code = :calc_code"
    df = read_table(engine, query, params={"calc_code": calc_code})

    if df.is_empty():
        raise ValueError(
            f"Calculation code '{calc_code}' not found in metrics.calculations"
        )

    calc_id = str(df[0, "id"])
    _cache["calc_ids"][calc_code] = calc_id
    return calc_id


def get_definition_id(engine: Engine, metric_code: str) -> str:
    """Return UUID of definitions row by metric_code. Raise if not found."""
    if metric_code in _cache["def_ids"]:
        return _cache["def_ids"][metric_code]

    query = "SELECT id FROM metrics.definitions WHERE metric_code = :metric_code"
    df = read_table(engine, query, params={"metric_code": metric_code})

    if df.is_empty():
        raise ValueError(
            f"Metric definition code '{metric_code}' not found in metrics.definitions"
        )

    def_id = str(df[0, "id"])
    _cache["def_ids"][metric_code] = def_id
    return def_id


def get_project_agg_id(engine: Engine, project_id: str) -> str:
    """Return dim_projects.id for given clean_jira project_id. Raise if not found."""
    if project_id in _cache["project_agg_ids"]:
        return _cache["project_agg_ids"][project_id]

    query = "SELECT id FROM metrics.dim_projects WHERE project_id = :project_id"
    df = read_table(engine, query, params={"project_id": project_id})

    if df.is_empty():
        # Try to resolve project key to create it
        key_query = "SELECT project_key FROM clean_jira.projects WHERE id = :project_id"
        key_df = read_table(engine, key_query, params={"project_id": project_id})
        if key_df.is_empty():
            raise ValueError(
                f"Project ID '{project_id}' not found in clean_jira.projects"
            )

        project_key = key_df[0, "project_key"]
        return get_or_create_dim_project(engine, project_id, project_key)

    agg_id = str(df[0, "id"])
    _cache["project_agg_ids"][project_id] = agg_id
    return agg_id


def get_or_create_dim_project(engine: Engine, project_id: str, project_key: str) -> str:
    """Upsert dim_projects row, return id."""
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO metrics.dim_projects (project_id, project_key)
                VALUES (:project_id, :project_key)
                ON CONFLICT (project_id) DO UPDATE SET project_key = EXCLUDED.project_key
            """
            ),
            {"project_id": project_id, "project_key": project_key},
        )

    query = "SELECT id FROM metrics.dim_projects WHERE project_id = :project_id"
    df = read_table(engine, query, params={"project_id": project_id})
    agg_id = str(df[0, "id"])
    _cache["project_agg_ids"][project_id] = agg_id
    return agg_id


def resolve_commitment_rule(
    engine: Engine, project_id: str, board_id: str, calc_code: str
) -> Optional[str]:
    """
    Return commitment_rules.id for given project/board/calc_code.
    Priority: project+board > project only > global (project_id=NULL).
    Returns None if no rule found.
    """
    calc_id = get_calculation_id(engine, calc_code)

    query = """
        SELECT id, project_id, board_id
        FROM metrics.commitment_rules
        WHERE target_calculation_id = :calc_id
          AND (project_id = :project_id OR project_id IS NULL)
          AND (board_id = :board_id OR board_id IS NULL)
        ORDER BY
            (project_id IS NOT NULL)::int DESC,
            (board_id IS NOT NULL)::int DESC
        LIMIT 1
    """
    df = read_table(
        engine,
        query,
        params={"calc_id": calc_id, "project_id": project_id, "board_id": board_id},
    )

    if df.is_empty():
        return None

    return str(df[0, "id"])


def resolve_unit_field(
    engine: Engine, project_id: str, unit_code: str
) -> Optional[dict]:
    """
    Return {'source_field_id': uuid, 'source_entity': str} for given project/unit_code.
    Falls back to global (project_id=NULL) rule.
    Returns None if no config found.
    """
    query = """
        SELECT source_field_id, source_entity
        FROM metrics.units
        WHERE unit_code = :unit_code
          AND (project_id = :project_id OR project_id IS NULL)
        ORDER BY (project_id IS NOT NULL)::int DESC
        LIMIT 1
    """
    df = read_table(
        engine, query, params={"unit_code": unit_code, "project_id": project_id}
    )

    if df.is_empty():
        return None

    return {
        "source_field_id": str(df[0, "source_field_id"])
        if df[0, "source_field_id"]
        else None,
        "source_entity": df[0, "source_entity"],
    }
