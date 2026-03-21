import polars as pl


def calculate_defect_density(
    sprints_df: pl.DataFrame,
    sprint_issues_df: pl.DataFrame,
    issues_df: pl.DataFrame,
    issue_types_df: pl.DataFrame,
    numerator_type: str,
    denominator_type: str,
) -> pl.DataFrame:
    """
    Calculate ratio of numerator_type issues to denominator_type issues per sprint.
    """
    # Join issues with types
    issues_with_types = issues_df.join(
        issue_types_df.select(["id", "name"]).rename(
            {"id": "issue_type_id", "name": "type_name"}
        ),
        on="issue_type_id",
        how="left",
    )

    # Map to sprints
    sprint_full = sprint_issues_df.join(
        issues_with_types.select(["id", "type_name"]),
        left_on="issue_id",
        right_on="id",
        how="inner",
    )

    agg = (
        sprint_full.group_by("sprint_id")
        .agg(
            [
                pl.col("issue_id")
                .filter(
                    pl.col("type_name").cast(pl.Utf8).str.to_lowercase()
                    == numerator_type.lower()
                )
                .count()
                .alias("n"),
                pl.col("issue_id")
                .filter(
                    pl.col("type_name").cast(pl.Utf8).str.to_lowercase()
                    == denominator_type.lower()
                )
                .count()
                .alias("d"),
            ]
        )
        .with_columns(
            pl.when(pl.col("d") > 0)
            .then(pl.col("n").cast(pl.Float64) / pl.col("d").cast(pl.Float64))
            .otherwise(0.0)
            .alias("density_ratio")
        )
    )

    result = (
        sprints_df.select(
            ["project_id", pl.col("id").alias("iteration_id"), "start_date"]
        )
        .join(agg, left_on="iteration_id", right_on="sprint_id", how="left")
        .with_columns(pl.col("density_ratio").fill_null(0.0))
    )

    return result


def calculate_backflow_rate(
    sprints_df: pl.DataFrame,
    sprint_issues_df: pl.DataFrame,
    issue_status_changelog_df: pl.DataFrame,
    board_columns_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Percentage of backward transitions relative to total transitions per sprint.
    """
    if issue_status_changelog_df.is_empty() or board_columns_df.is_empty():
        return sprints_df.select(
            ["project_id", pl.col("id").alias("iteration_id"), "start_date"]
        ).with_columns(pl.lit(0.0).alias("backflow_pct"))

    # If board_columns_df has individual status_id rows (standard format), aggregate them
    if (
        "status_id" in board_columns_df.columns
        and "status_ids" not in board_columns_df.columns
    ):
        board_columns_df = board_columns_df.group_by(
            ["id", "board_id", "name", "position"]
        ).agg(pl.col("status_id").alias("status_ids"))

    # status_id -> position mapping
    # board_columns_df.status_ids is array
    status_pos = (
        board_columns_df.explode("status_ids")
        .select([pl.col("status_ids").alias("status_id"), "position"])
        .filter(pl.col("status_id").is_not_null())
    )

    # Map transitions to positions
    # BUG-1: Slim changelog to avoid 'id' collision in cross-join
    cl_slim = issue_status_changelog_df.select(
        ["issue_id", "from_status_id", "to_status_id", "changed_at"]
    )
    transitions = cl_slim.join(
        status_pos.rename({"status_id": "from_status_id", "position": "from_pos"}),
        on="from_status_id",
        how="inner",
    ).join(
        status_pos.rename({"status_id": "to_status_id", "position": "to_pos"}),
        on="to_status_id",
        how="inner",
    )

    transitions = transitions.with_columns(
        (pl.col("to_pos") < pl.col("from_pos")).alias("is_backward")
    )

    # Map to sprints
    transitions_with_sprints = transitions.join(
        sprints_df.select(["id", "start_date", "end_date"]), how="cross"
    ).filter(
        (pl.col("changed_at") > pl.col("start_date"))
        & (pl.col("changed_at") <= pl.col("end_date"))
    )

    # Ensure issues in sprint
    transitions_with_sprints = transitions_with_sprints.join(
        sprint_issues_df,
        left_on=["issue_id", "id"],
        right_on=["issue_id", "sprint_id"],
        how="inner",
    )

    agg = (
        transitions_with_sprints.group_by("id")
        .agg(
            [
                pl.col("issue_id").count().alias("total_trans"),
                pl.col("is_backward").sum().alias("backward_count"),
            ]
        )
        .with_columns(
            # BUG-4: Division by zero guard
            pl.when(pl.col("total_trans") > 0)
            .then(
                pl.col("backward_count").cast(pl.Float64)
                / pl.col("total_trans").cast(pl.Float64)
                * 100
            )
            .otherwise(0.0)
            .alias("backflow_pct")
        )
    )

    result = (
        sprints_df.select(
            ["project_id", pl.col("id").alias("iteration_id"), "start_date"]
        )
        .join(agg, left_on="iteration_id", right_on="id", how="left")
        .with_columns(pl.col("backflow_pct").fill_null(0.0))
    )

    return result
