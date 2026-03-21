"""
Time to Market Calculations utility.
Provides logic to load TTM-specific settings from the database.
"""

import json

import polars as pl

from pipelines.utils.polars_db import read_table


def _parse_settings(settings) -> list[str]:
    """Parse JSON setting if string, and return 'include' key as list."""
    if isinstance(settings, str):
        try:
            settings = json.loads(settings)
        except Exception:
            return ["Epic"]
    if not isinstance(settings, dict):
        return ["Epic"]
    return settings.get("include", ["Epic"])


def load_issue_type_filter(engine, calc_code: str, project_id: str = None) -> list[str]:
    """
    Load issue type names from calculation_settings for a given calc_code.
    Priority: project-specific setting > global setting.
    Returns list of type names (e.g., ["Epic"]).
    Fallback: ["Epic"] if no settings found.
    """
    query = """
        SELECT s.project_id, s.settings_json
        FROM metrics.calculation_settings s
        JOIN metrics.calculations c ON s.target_calculation_id = c.id
        WHERE c.calc_code = :calc_code
          AND s.settings_type = 'issue_type_filter'
          AND s.enabled = true
          AND (s.project_id = :project_id OR s.project_id IS NULL)
    """

    params = {"calc_code": calc_code, "project_id": project_id}
    df = read_table(engine, query, params=params)

    if df.is_empty():
        return ["Epic"]

    # 1. Project-specific priority
    if project_id:
        project_rows = df.filter(pl.col("project_id").is_not_null())
        if not project_rows.is_empty():
            return _parse_settings(project_rows["settings_json"][0])

    # 2. Global fallback (NULL project_id)
    global_rows = df.filter(pl.col("project_id").is_null())
    if not global_rows.is_empty():
        return _parse_settings(global_rows["settings_json"][0])

    return ["Epic"]
