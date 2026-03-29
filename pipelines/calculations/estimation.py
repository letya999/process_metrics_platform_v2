import polars as pl


def calculate_estimate_volatility(
    issues_df: pl.DataFrame,
    field_value_changelog_df: pl.DataFrame,
    field_values_df: pl.DataFrame,
    sp_field_key_id: str,
) -> pl.DataFrame:
    """
    Calculate absolute difference between initial and final SP per issue.
    """
    # 1. Final SP
    final_sp = field_values_df.filter(pl.col("field_key_id") == sp_field_key_id).select(
        ["issue_id", pl.col("json_value").alias("final_sp_raw")]
    )

    # 2. Initial SP (from changelog)
    if not field_value_changelog_df.is_empty():
        sp_changes = field_value_changelog_df.filter(
            pl.col("field_key_id") == sp_field_key_id
        ).sort("change_time")

        initial_sp = sp_changes.unique(subset="issue_id", keep="first").select(
            ["issue_id", pl.col("old_value").alias("initial_sp_raw")]
        )
    else:
        initial_sp = pl.DataFrame(
            schema={"issue_id": pl.Utf8, "initial_sp_raw": pl.Utf8}
        )

    # Join with issues
    issues = issues_df.select(["id", "issue_key", "project_id"]).rename(
        {"id": "issue_id"}
    )

    result = issues.join(final_sp, on="issue_id", how="left", coalesce=True).join(
        initial_sp, on="issue_id", how="left", coalesce=True
    )

    # If no initial_sp in changelog, it means it was never changed, so initial = final
    result = result.with_columns(
        pl.col("initial_sp_raw").fill_null(pl.col("final_sp_raw"))
    )

    # Parse to float
    def parse_sp(col_name):
        return (
            pl.when(
                pl.col(col_name).is_not_null()
                & pl.col(col_name)
                .cast(pl.Utf8)
                .str.strip_chars()
                .str.contains(r"^-?[0-9]+\.?[0-9]*$")
            )
            .then(
                pl.col(col_name)
                .cast(pl.Utf8)
                .str.strip_chars()
                .cast(pl.Float64, strict=False)
            )
            .otherwise(0.0)
        )

    result = result.with_columns(
        [
            parse_sp("final_sp_raw").alias("final_sp"),
            parse_sp("initial_sp_raw").alias("initial_sp"),
        ]
    )

    result = result.with_columns(
        (pl.col("final_sp") - pl.col("initial_sp")).abs().alias("volatility")
    )

    return result
