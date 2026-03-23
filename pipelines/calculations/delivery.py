from datetime import date, datetime, timedelta
from typing import List, Optional

import polars as pl


def _to_date(v):
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        return date.fromisoformat(v[:10])
    return v


def calculate_release_burnup(
    issues_df: pl.DataFrame,
    issue_status_changelog_df: pl.DataFrame,
    done_status_ids: List[str],
    field_values_df: pl.DataFrame,
    field_keys_df: pl.DataFrame,
    field_value_changelog_df: pl.DataFrame,
    fix_versions_df: Optional[pl.DataFrame] = None,
) -> pl.DataFrame:
    """
    Calculate scope and done SP per version per day using vectorized Polars operations.
    """
    if fix_versions_df is None or fix_versions_df.is_empty():
        return pl.DataFrame(
            schema={
                "project_id": pl.Utf8,
                "version_name": pl.Utf8,
                "time_date": pl.Date,
                "scope_sp": pl.Float64,
                "done_sp": pl.Float64,
            }
        )

    from pipelines.calculations.velocity import extract_story_points

    current_sp_df = extract_story_points(issues_df, field_values_df, field_keys_df)

    # Join issues with versions
    issues_with_versions = fix_versions_df.join(
        issues_df.select(["id", "project_id", "created_at"]),
        left_on="issue_id",
        right_on="id",
        how="inner",
    ).with_columns(pl.col("created_at").dt.date().alias("created_date"))

    # 1. Completion date for each issue
    done_transitions = (
        issue_status_changelog_df.filter(
            pl.col("to_status_id")
            .cast(pl.Utf8)
            .str.to_lowercase()
            .is_in([s.lower() for s in done_status_ids])
        )
        .sort("changed_at")
        .unique(subset="issue_id", keep="first")
        .select(["issue_id", pl.col("changed_at").dt.date().alias("done_date")])
    )

    issues_full = (
        issues_with_versions.join(current_sp_df, on="issue_id", how="left")
        .join(done_transitions, on="issue_id", how="left")
        .with_columns(pl.col("story_points").fill_null(0.0))
    )

    all_data = []
    versions = issues_full.select(["project_id", "version_name"]).unique().to_dicts()

    today = date.today()
    two_years_ago = today - timedelta(days=730)

    for v in versions:
        v_name = v["version_name"]
        proj_id = v["project_id"]
        v_issues_data = issues_full.filter(
            (pl.col("version_name") == v_name) & (pl.col("project_id") == proj_id)
        )

        if v_issues_data.is_empty():
            continue

        min_created = v_issues_data.select(pl.col("created_date").min()).item()
        start_date = max(
            _to_date(min_created) if min_created is not None else two_years_ago,
            two_years_ago,
        )
        end_date = today

        # Generate date range
        date_series = pl.date_range(start_date, end_date, "1d", eager=True).alias(
            "time_date"
        )
        df_dates = pl.DataFrame(date_series)

        # Scope: added on created_date
        scope_by_date = (
            v_issues_data.group_by("created_date")
            .agg(pl.col("story_points").sum().alias("added_sp"))
            .rename({"created_date": "time_date"})
        )

        # Done: finished on done_date
        done_by_date = (
            v_issues_data.filter(pl.col("done_date").is_not_null())
            .group_by("done_date")
            .agg(pl.col("story_points").sum().alias("added_done_sp"))
            .rename({"done_date": "time_date"})
        )

        v_result = (
            df_dates.join(scope_by_date, on="time_date", how="left")
            .join(done_by_date, on="time_date", how="left")
            .with_columns(
                [
                    pl.col("added_sp").fill_null(0.0).cum_sum().alias("scope_sp"),
                    pl.col("added_done_sp").fill_null(0.0).cum_sum().alias("done_sp"),
                ]
            )
            .with_columns(
                [
                    pl.lit(proj_id).alias("project_id"),
                    pl.lit(v_name).alias("version_name"),
                ]
            )
            .select(["project_id", "version_name", "time_date", "scope_sp", "done_sp"])
        )

        all_data.append(v_result)

    if not all_data:
        return pl.DataFrame(
            schema={
                "project_id": pl.Utf8,
                "version_name": pl.Utf8,
                "time_date": pl.Date,
                "scope_sp": pl.Float64,
                "done_sp": pl.Float64,
            }
        )

    return pl.concat(all_data)
