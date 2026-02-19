from typing import List, Optional

import polars as pl


def get_slice_rules(
    conn_str_or_engine,
    project_id: Optional[str] = None,
    target_metric_table: Optional[str] = None,
) -> pl.DataFrame:
    """
    Fetch slice rules from the database.
    Merge specific project rules and default global rules.
    """
    query = """
    SELECT
        id,
        project_id,
        target_metric_table,
        slice_table_name,
        rule_name,
        source_table,
        group_by_column,
        filter_condition,
        enabled
    FROM metrics.metric_slice_rules
    WHERE enabled = true
    """

    # In a real scenario, we might want to fetch all and filter in memory if the table is small,
    # or filter in SQL. Here we'll fetch all active rules and filter in Python for flexibility
    # as we need to handle the "default" logic which involves checking for NULLs and specific strings.

    try:
        rules_df = pl.read_database(query, conn_str_or_engine)
    except Exception as e:
        # Fallback if connection string/engine handling varies or table doesn't exist yet (tests)
        print(f"Error fetching rules: {e}")
        return pl.DataFrame()

    if rules_df.is_empty():
        return rules_df

    # Filter logic
    # We want rules that:
    # 1. Match the specific project_id OR have project_id as NULL (global)
    # 2. Match the specific metric table OR have target_metric_table as 'default'

    filtered_rules = rules_df.filter(
        (pl.col("project_id").is_null() | (pl.col("project_id") == project_id))
        & (
            (pl.col("target_metric_table") == "default")
            | (pl.col("target_metric_table") == target_metric_table)
        )
    )

    return filtered_rules


def apply_slicing(
    df: pl.DataFrame,
    rules_df: pl.DataFrame,
    calculation_func,
    base_columns: List[
        str
    ] = None,  # Not strictly needed if calculation_func handles returning key columns, but useful for context
) -> pl.DataFrame:
    """
    Apply slicing rules to a DataFrame by iterating over slice values and applying the calculation logic.

    Args:
        df: Base DataFrame.
        rules_df: Rules DataFrame.
        calculation_func: Function that takes (filtered_df) and returns a DataFrame of metrics.
        base_columns: Optional list of columns to ensure are in the output if calculation_func doesn't preserve them (not used in this simplified version).

    Returns:
        concatenated DataFrame with slice_rule_name and slice_value.
    """
    if df.is_empty() or rules_df.is_empty():
        return pl.DataFrame()

    sliced_frames = []

    rules = rules_df.to_dicts()

    for rule in rules:
        rule_name = rule["rule_name"]
        group_col = rule["group_by_column"]
        source_table = rule.get("source_table", "")
        rule_project_id = rule.get("project_id")

        # --- Robust Column Matching Logic ---
        df_cols_lower = {c.lower(): c for c in df.columns}
        target_col = None

        # 1. Direct match
        if group_col in df.columns:
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
        # If the rule is specific to a project, filter data to that project
        if rule_project_id is not None and "project_id" in df.columns:
            rule_df = df.filter(pl.col("project_id") == rule_project_id)
            if rule_df.is_empty():
                continue

            projects_to_process = [rule_project_id]
        else:
            # Global rule: process all projects in df individually to respect project-specific values
            rule_df = df
            if "project_id" in df.columns:
                projects_to_process = (
                    df.select("project_id").unique().drop_nulls().to_series().to_list()
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
                        pl.lit(rule_name).alias("slice_rule_name"),
                        pl.lit(str(val)).alias("slice_value"),
                    ]
                )

                # Ensure project_id is preserved if it was missing in calculation result but present in p_id
                if "project_id" not in result_df.columns and p_id is not None:
                    result_df = result_df.with_columns(pl.lit(p_id).alias("project_id"))

                sliced_frames.append(result_df)

    if not sliced_frames:
        return pl.DataFrame()

    return pl.concat(sliced_frames)
