from typing import Any, Optional

import polars as pl
from sqlalchemy import Engine

from ..utils.polars_db import read_table


def get_slice_rules(
    engine: Engine,
    project_id: Optional[str] = None,
    target_definition_id: Optional[str] = None,
) -> pl.DataFrame:
    """
    Fetch slice rules from the database.
    Merge specific project rules and default global rules.
    """
    query = """
    SELECT
        id as slice_rule_id,
        project_id,
        target_definition_id,
        rule_name as slice_rule_name,
        source_table,
        group_by_source_column as group_by_column,
        enabled
    FROM metrics.slice_rules
    WHERE enabled = true
    """

    try:
        rules_df = read_table(engine, query)
    except Exception as e:
        print(f"Error fetching rules: {e}")
        return pl.DataFrame()

    if rules_df.is_empty():
        return rules_df

    # Filter logic:
    # 1. Match the specific project_id OR have project_id as NULL (global)
    # 2. Match the specific target_definition_id OR have target_definition_id as NULL (default for all metrics)

    # Cast to string for comparison if they are UUIDs
    rules_df = rules_df.with_columns(
        [
            pl.col("project_id").cast(pl.Utf8),
            pl.col("target_definition_id").cast(pl.Utf8),
        ]
    )

    filtered_rules = rules_df.filter(
        (pl.col("project_id").is_null() | (pl.col("project_id") == str(project_id)))
        & (
            pl.col("target_definition_id").is_null()
            | (pl.col("target_definition_id") == str(target_definition_id))
        )
    )

    return filtered_rules


def apply_slicing(
    df: pl.DataFrame,
    rules_df: pl.DataFrame,
    calculation_func: Any,
) -> pl.DataFrame:
    """
    Apply slicing rules to a DataFrame by iterating over slice values and applying the calculation logic.

    Args:
        df: Base DataFrame.
        rules_df: Rules DataFrame.
        calculation_func: Function that takes (filtered_df) and returns a DataFrame of metrics.

    Returns:
        concatenated DataFrame with slice_rule_id, slice_rule_name and slice_value.
    """
    if df.is_empty() or rules_df.is_empty():
        return pl.DataFrame()

    sliced_frames = []

    rules = rules_df.to_dicts()

    for rule in rules:
        rule_id = rule["slice_rule_id"]
        rule_name = rule["slice_rule_name"]
        group_col = rule["group_by_column"]
        source_table = rule.get("source_table", "")
        rule_project_id = rule.get("project_id")

        current_rule_df = df

        # --- Robust Column Matching Logic ---
        df_cols_lower = {c.lower(): c for c in current_rule_df.columns}
        target_col = None

        # 1. Direct match
        if group_col in current_rule_df.columns:
            target_col = group_col
        else:
            # 2. Heuristic match
            table_name = (source_table or "").split(".")[-1].lower()
            if table_name:
                singular = table_name.rstrip("s")
                candidates = [f"{singular}_{group_col.lower()}", singular]
                if singular.startswith("issue_"):
                    short_singular = singular.replace("issue_", "")
                    candidates.append(f"{short_singular}_{group_col.lower()}")
                    candidates.append(short_singular)

                for cand in candidates:
                    if cand in df_cols_lower:
                        target_col = df_cols_lower[cand]
                        break

        if not target_col:
            continue

        # --- Project-Aware Slicing ---
        if rule_project_id is not None and "project_id" in current_rule_df.columns:
            rule_df = current_rule_df.filter(pl.col("project_id") == rule_project_id)
            if rule_df.is_empty():
                continue

            projects_to_process = [rule_project_id]
        else:
            rule_df = current_rule_df
            if "project_id" in current_rule_df.columns:
                projects_to_process = (
                    current_rule_df.select("project_id")
                    .unique()
                    .drop_nulls()
                    .to_series()
                    .to_list()
                )
            else:
                projects_to_process = [None]

        for p_id in projects_to_process:
            p_df = rule_df
            if p_id is not None and "project_id" in rule_df.columns:
                p_df = rule_df.filter(pl.col("project_id") == p_id)

            if p_df.is_empty():
                continue

            # Get unique values for THIS project
            unique_values = (
                p_df.select(pl.col(target_col))
                .unique()
                .drop_nulls()
                .to_series()
                .to_list()
            )

            for val in unique_values:
                subset_df = p_df.filter(pl.col(target_col) == val)
                if subset_df.is_empty():
                    continue

                metrics_df = calculation_func(subset_df)
                if metrics_df.is_empty():
                    continue

                result_df = metrics_df.with_columns(
                    [
                        pl.lit(rule_id).alias("slice_rule_id"),
                        pl.lit(rule_name).alias("slice_rule_name"),
                        pl.lit(str(val)).alias("slice_value"),
                    ]
                )

                # Ensure project_id is preserved
                if "project_id" not in result_df.columns and p_id is not None:
                    result_df = result_df.with_columns(pl.lit(p_id).alias("project_id"))

                sliced_frames.append(result_df)

    if not sliced_frames:
        return pl.DataFrame()

    return pl.concat(sliced_frames)
