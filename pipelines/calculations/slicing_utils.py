from typing import Any, Optional

import polars as pl
from sqlalchemy import Engine

from ..utils.polars_db import read_table
from ..utils.smart_slicer import SmartSlicer


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

    # Cast to string for comparison and consistent concatenation.
    # fill_null("null") handles real SQL NULLs; str.replace handles "None" strings
    # produced by the pandas fallback path in read_table (pd.astype(str) converts
    # None -> "None" instead of keeping it as a real null).
    rules_df = rules_df.with_columns(
        [
            pl.col("slice_rule_id").cast(pl.Utf8),
            pl.col("project_id")
            .cast(pl.Utf8)
            .fill_null("null")
            .str.replace("^None$", "null"),
            pl.col("target_definition_id")
            .cast(pl.Utf8)
            .fill_null("null")
            .str.replace("^None$", "null"),
        ]
    )

    p_id_str = str(project_id) if project_id else "null"
    d_id_str = str(target_definition_id) if target_definition_id else "null"

    filtered_rules = rules_df.filter(
        ((pl.col("project_id") == "null") | (pl.col("project_id") == p_id_str))
        & (
            (pl.col("target_definition_id") == "null")
            | (pl.col("target_definition_id") == d_id_str)
        )
    )

    return filtered_rules


def apply_slicing(
    df: pl.DataFrame,
    rules_df: pl.DataFrame,
    calculation_func: Any,
    engine: Engine,
    source_table: str = "clean_jira.issues",
) -> pl.DataFrame:
    """
    Apply slicing rules to a DataFrame.
    If the slice column is missing in the DF, it uses SmartSlicer to dynamically
    resolve the join path and inject the dimension.
    """
    if df.is_empty() or rules_df.is_empty():
        return pl.DataFrame()

    slicer = SmartSlicer(engine)
    sliced_frames = []
    rules = rules_df.to_dicts()

    for rule in rules:
        rule_id = rule["slice_rule_id"]
        rule_name = rule["slice_rule_name"]
        group_col = rule["group_by_column"]
        rule_project_id = rule.get("project_id")

        # 1. Determine if we need to inject the dimension
        df_cols_lower = {c.lower(): c for c in df.columns}
        target_col = None

        # Check if it's already in the DataFrame
        if group_col.lower() in df_cols_lower:
            target_col = df_cols_lower[group_col.lower()]
        elif f"{group_col.lower()}_name" in df_cols_lower:
            target_col = df_cols_lower[f"{group_col.lower()}_name"]
        else:
            # BUG #4: Try suffix: 'issue_type' -> 'type' -> 'type_name'
            parts = group_col.lower().split("_")
            for i in range(1, len(parts)):
                suffix = "_".join(parts[i:])
                if suffix in df_cols_lower:
                    target_col = df_cols_lower[suffix]
                    break
                if f"{suffix}_name" in df_cols_lower:
                    target_col = df_cols_lower[f"{suffix}_name"]
                    break

        # 2. If not in DF, resolve via SmartSlicer (Dynamic Join Path)
        current_df = df
        if not target_col:
            # BUG #3: Fix SmartSlicer full_target construction
            if "." in group_col:
                # If group_col looks like 'table.column', use it with schema from source_table
                schema = source_table.split(".")[0]
                full_target = f"{schema}.{group_col}"
            else:
                # Use find_target_for_column to search for the column in adjacent tables
                full_target = slicer.find_target_for_column(source_table, group_col)

            if not full_target:
                print(
                    f"Warning: Cannot resolve target for column '{group_col}' from {source_table}"
                )
                continue

            mapping_df = slicer.get_slice_mapping(source_table, full_target)

            if mapping_df is not None and not mapping_df.is_empty():
                # Robust Join: cast both to string to avoid UUID type mismatch
                mapping_df = mapping_df.with_columns(pl.col("source_id").cast(pl.Utf8))
                current_df = df.with_columns(pl.col("id").cast(pl.Utf8)).join(
                    mapping_df,
                    left_on="id",
                    right_on="source_id",
                    how="left",
                    coalesce=True,
                )
                target_col = "slice_value"
            else:
                continue

        # 3. Process projects and slices
        projects = [None]
        if "project_id" in current_df.columns:
            if rule_project_id and rule_project_id != "null":
                projects = [rule_project_id]
            else:
                projects = (
                    current_df.select("project_id")
                    .unique()
                    .drop_nulls()
                    .to_series()
                    .to_list()
                )

        for p_id in projects:
            p_df = (
                current_df.filter(pl.col("project_id") == p_id) if p_id else current_df
            )
            if p_df.is_empty():
                continue

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

                # Add slicing context
                result_df = metrics_df.with_columns(
                    [
                        pl.lit(rule_id).alias("slice_rule_id"),
                        pl.lit(rule_name).alias("slice_rule_name"),
                        pl.lit(str(val)).alias("slice_value"),
                    ]
                )

                if "project_id" not in result_df.columns and p_id:
                    result_df = result_df.with_columns(pl.lit(p_id).alias("project_id"))

                sliced_frames.append(result_df)

    if not sliced_frames:
        return pl.DataFrame()

    return pl.concat(sliced_frames)
