from datetime import date, datetime, timedelta
from typing import List

import polars as pl

from pipelines.calculations.velocity import (
    determine_story_points_at_date,
    extract_story_points,
    identify_completed_issues,
    identify_sprint_commitment,
    identify_sprint_final_scope,
)


def _to_date(v):
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        return date.fromisoformat(v[:10])
    return v


def _ensure_complete_date(df: pl.DataFrame) -> pl.DataFrame:
    """Ensure complete_date column exists, adding null column if missing."""
    if "complete_date" not in df.columns:
        return df.with_columns(
            pl.lit(None).cast(pl.Datetime("us")).alias("complete_date")
        )
    return df


def calculate_sprint_scope_changes(
    sprints_df: pl.DataFrame,
    sprint_changelog_df: pl.DataFrame,
    issues_df: pl.DataFrame,
    field_values_df: pl.DataFrame,
    field_keys_df: pl.DataFrame,
    field_value_changelog_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Calculate issues added and removed during the sprint.
    """
    if sprint_changelog_df.is_empty():
        return pl.DataFrame(
            schema={
                "project_id": pl.Utf8,
                "iteration_id": pl.Utf8,
                "iteration_name": pl.Utf8,
                "start_date": pl.Datetime,
                "added_count": pl.Int64,
                "added_sp": pl.Float64,
                "removed_count": pl.Int64,
                "removed_sp": pl.Float64,
            }
        )

    # Join changelog with sprint dates
    cl_with_dates = sprint_changelog_df.join(
        sprints_df.select(["id", "start_date", "end_date"]),
        left_on="sprint_id",
        right_on="id",
        how="inner",
    )

    # Added issues: action='added' AND change_time > sprint.start_date AND change_time <= sprint.end_date
    added_cl = cl_with_dates.filter(
        (pl.col("action") == "added")
        & (pl.col("changed_at") > pl.col("start_date"))
        & (pl.col("changed_at") <= pl.col("end_date"))
    ).select(["issue_id", "sprint_id", "changed_at"])

    # Removed issues: action='removed' AND change_time > sprint.start_date AND change_time <= sprint.end_date
    removed_cl = cl_with_dates.filter(
        (pl.col("action") == "removed")
        & (pl.col("changed_at") > pl.col("start_date"))
        & (pl.col("changed_at") <= pl.col("end_date"))
    ).select(["issue_id", "sprint_id", "changed_at"])

    # Calculate SP for added issues at the time they were added (or end of sprint as proxy)

    # We need current_sp_df for determine_story_points_at_date
    current_sp_df = extract_story_points(issues_df, field_values_df, field_keys_df)

    # For added issues, we use SP at the time of addition if possible,
    # but determine_story_points_at_date works per sprint.
    # Let's use the sprint end date as a proxy for SP value of scope creep.
    sprints_safe = _ensure_complete_date(sprints_df)
    sprints_with_eff_end = sprints_safe.with_columns(
        pl.coalesce(["complete_date", "end_date"]).alias("effective_end_date")
    )

    added_with_sp = determine_story_points_at_date(
        added_cl.select(["issue_id", "sprint_id"]),
        sprints_with_eff_end,
        current_sp_df,
        field_value_changelog_df,
        field_keys_df,
        date_col="effective_end_date",
    )

    removed_with_sp = determine_story_points_at_date(
        removed_cl.select(["issue_id", "sprint_id"]),
        sprints_with_eff_end,
        current_sp_df,
        field_value_changelog_df,
        field_keys_df,
        date_col="effective_end_date",
    )

    added_agg = added_with_sp.group_by("sprint_id").agg(
        [
            pl.col("issue_id").count().alias("added_count"),
            pl.col("story_points").sum().alias("added_sp"),
        ]
    )

    removed_agg = removed_with_sp.group_by("sprint_id").agg(
        [
            pl.col("issue_id").count().alias("removed_count"),
            pl.col("story_points").sum().alias("removed_sp"),
        ]
    )

    result = (
        sprints_df.select(
            [
                "project_id",
                pl.col("id").alias("iteration_id"),
                pl.col("name").alias("iteration_name"),
                "start_date",
            ]
        )
        .join(added_agg, left_on="iteration_id", right_on="sprint_id", how="left")
        .join(removed_agg, left_on="iteration_id", right_on="sprint_id", how="left")
        .with_columns(
            [
                pl.col("added_count").fill_null(0),
                pl.col("added_sp").fill_null(0.0),
                pl.col("removed_count").fill_null(0),
                pl.col("removed_sp").fill_null(0.0),
            ]
        )
    )

    return result


def calculate_sprint_spillover(
    sprints_df: pl.DataFrame, sprint_issues_df: pl.DataFrame
) -> pl.DataFrame:
    """
    Count issues that appear in more than one sprint.
    """
    if sprint_issues_df.is_empty():
        return sprints_df.select(
            [
                "project_id",
                pl.col("id").alias("iteration_id"),
                pl.col("name").alias("iteration_name"),
                "start_date",
            ]
        ).with_columns(pl.lit(0).alias("spillover_count"))

    # Group by issue_id, count distinct sprint_ids
    issue_sprint_counts = sprint_issues_df.group_by("issue_id").agg(
        pl.col("sprint_id").n_unique().alias("sprint_count")
    )

    # Issues with count > 1 are spillover candidates
    spillover_issues = issue_sprint_counts.filter(pl.col("sprint_count") > 1).select(
        "issue_id"
    )

    # Join back to sprint context to see which sprints these issues belong to
    spillover_by_sprint = (
        sprint_issues_df.join(spillover_issues, on="issue_id", how="inner")
        .group_by("sprint_id")
        .agg(pl.col("issue_id").count().alias("spillover_count"))
    )

    result = (
        sprints_df.select(
            [
                "project_id",
                pl.col("id").alias("iteration_id"),
                pl.col("name").alias("iteration_name"),
                "start_date",
            ]
        )
        .join(
            spillover_by_sprint,
            left_on="iteration_id",
            right_on="sprint_id",
            how="left",
        )
        .with_columns(pl.col("spillover_count").fill_null(0))
    )

    return result


def calculate_sprint_burndown(
    sprints_df: pl.DataFrame,
    sprint_issues_df: pl.DataFrame,
    sprint_changelog_df: pl.DataFrame,
    issue_status_changelog_df: pl.DataFrame,
    done_status_ids: List[str],
    issues_df: pl.DataFrame,
    field_values_df: pl.DataFrame,
    field_keys_df: pl.DataFrame,
    field_value_changelog_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Calculate remaining SP per day for each sprint.
    """
    current_sp_df = extract_story_points(issues_df, field_values_df, field_keys_df)

    # 1. Total planned SP (commitment)
    commitment_df = identify_sprint_commitment(
        sprint_changelog_df, sprints_df, issues_df, sprint_issues_df
    )
    commitment_with_sp = determine_story_points_at_date(
        commitment_df,
        sprints_df,
        current_sp_df,
        field_value_changelog_df,
        field_keys_df,
        date_col="start_date",
    )

    total_planned_sp = commitment_with_sp.group_by("sprint_id").agg(
        pl.col("story_points").sum().alias("total_sp")
    )

    # 2. Daily completions
    # We need issues that transitioned to done status DURING the sprint
    # BUG-1: Slim changelog to avoid 'id' collision in cross-join
    status_slim = issue_status_changelog_df.select(
        ["issue_id", "to_status_id", "changed_at"]
    )
    cl_with_dates = status_slim.join(
        sprints_df.select(["id", "start_date", "end_date"]),
        how="cross",  # Note: small optimization could be done here but cross join is simple for logic
    ).filter(
        (pl.col("changed_at") > pl.col("start_date"))
        & (pl.col("changed_at") <= pl.col("end_date"))
        & (
            pl.col("to_status_id")
            .cast(pl.Utf8)
            .str.to_lowercase()
            .is_in([s.lower() for s in done_status_ids])
        )
    )

    # Ensure issues were in the sprint
    cl_with_dates = cl_with_dates.join(
        sprint_issues_df,
        left_on=["issue_id", "id"],
        right_on=["issue_id", "sprint_id"],
        how="inner",
    )

    # Get SP for these issues at end of sprint
    # BUG-2: Ensure complete_date exists
    sprints_safe = _ensure_complete_date(sprints_df)
    completions_with_sp = determine_story_points_at_date(
        cl_with_dates.select(["issue_id", "id"]).rename({"id": "sprint_id"}),
        sprints_safe.with_columns(
            pl.coalesce(["complete_date", "end_date"]).alias("effective_end_date")
        ),
        current_sp_df,
        field_value_changelog_df,
        field_keys_df,
        date_col="effective_end_date",
    )

    # Add change_time to completions
    completions_with_sp = completions_with_sp.join(
        cl_with_dates.select(["issue_id", "id", "changed_at"]).rename(
            {"id": "sprint_id"}
        ),
        on=["issue_id", "sprint_id"],
        how="inner",
    )

    completions_with_sp = completions_with_sp.with_columns(
        pl.col("changed_at").dt.date().alias("completion_date")
    )

    # 3. Generate daily rows
    all_rows = []
    for sprint in sprints_df.to_dicts():
        sprint_id = sprint["id"]
        start_date = _to_date(sprint["start_date"])
        end_date = _to_date(sprint.get("complete_date") or sprint.get("end_date"))

        sprint_total_sp = total_planned_sp.filter(pl.col("sprint_id") == sprint_id)[
            "total_sp"
        ]
        sprint_total_sp = sprint_total_sp[0] if not sprint_total_sp.is_empty() else 0.0

        sprint_completions = completions_with_sp.filter(
            pl.col("sprint_id") == sprint_id
        )

        current_date = start_date
        cumulative_done = 0.0
        while current_date <= end_date:
            done_today = sprint_completions.filter(
                pl.col("completion_date") == current_date
            )["story_points"].sum()
            cumulative_done += done_today or 0.0
            remaining = max(0.0, sprint_total_sp - cumulative_done)

            all_rows.append(
                {
                    "project_id": sprint["project_id"],
                    "iteration_id": sprint["id"],
                    "time_date": current_date,
                    "remaining_sp": remaining,
                }
            )
            current_date += timedelta(days=1)

    if not all_rows:
        return pl.DataFrame(
            schema={
                "project_id": pl.Utf8,
                "iteration_id": pl.Utf8,
                "time_date": pl.Date,
                "remaining_sp": pl.Float64,
            }
        )

    return pl.DataFrame(all_rows)


def calculate_activation_velocity(
    sprints_df: pl.DataFrame,
    sprint_issues_df: pl.DataFrame,
    sprint_changelog_df: pl.DataFrame,
    issue_status_changelog_df: pl.DataFrame,
    issues_df: pl.DataFrame,
    field_values_df: pl.DataFrame,
    field_keys_df: pl.DataFrame,
    field_value_changelog_df: pl.DataFrame,
    initial_status_id: str,
) -> pl.DataFrame:
    """
    Calculate activation velocity percentage per day.
    """
    current_sp_df = extract_story_points(issues_df, field_values_df, field_keys_df)

    # 1. Total planned SP (commitment)
    commitment_df = identify_sprint_commitment(
        sprint_changelog_df, sprints_df, issues_df, sprint_issues_df
    )
    commitment_with_sp = determine_story_points_at_date(
        commitment_df,
        sprints_df,
        current_sp_df,
        field_value_changelog_df,
        field_keys_df,
        date_col="start_date",
    )

    total_planned_sp = commitment_with_sp.group_by("sprint_id").agg(
        pl.col("story_points").sum().alias("total_sp")
    )

    # 2. Daily activations (moving FROM initial status)
    # BUG-1: Slim changelog to avoid 'id' collision in cross-join
    status_slim = issue_status_changelog_df.select(
        # Note: from_status_id may be NULL (e.g. 30% of Jira changelog for initial status)
        ["issue_id", "from_status_id", "to_status_id", "changed_at"]
    )
    cl_with_dates = status_slim.join(
        sprints_df.select(["id", "start_date", "end_date"]), how="cross"
    ).filter(
        (pl.col("changed_at") > pl.col("start_date"))
        & (pl.col("changed_at") <= pl.col("end_date"))
        & (
            pl.col("from_status_id").cast(pl.Utf8).str.to_lowercase()
            == initial_status_id.lower()
        )
    )

    cl_with_dates = cl_with_dates.join(
        sprint_issues_df,
        left_on=["issue_id", "id"],
        right_on=["issue_id", "sprint_id"],
        how="inner",
    )

    # BUG-2: Ensure complete_date exists
    sprints_safe = _ensure_complete_date(sprints_df)
    activations_with_sp = (
        determine_story_points_at_date(
            cl_with_dates.select(["issue_id", "id"]).rename({"id": "sprint_id"}),
            sprints_safe.with_columns(
                pl.coalesce(["complete_date", "end_date"]).alias("effective_end_date")
            ),
            current_sp_df,
            field_value_changelog_df,
            field_keys_df,
            date_col="effective_end_date",
        )
        .join(
            cl_with_dates.select(["issue_id", "id", "changed_at"]).rename(
                {"id": "sprint_id"}
            ),
            on=["issue_id", "sprint_id"],
            how="inner",
        )
        .with_columns(pl.col("changed_at").dt.date().alias("activation_date"))
    )

    # 3. Generate daily rows
    all_rows = []
    for sprint in sprints_df.to_dicts():
        sprint_id = sprint["id"]
        start_date = _to_date(sprint["start_date"])
        end_date = _to_date(sprint.get("complete_date") or sprint.get("end_date"))

        sprint_total_sp = total_planned_sp.filter(pl.col("sprint_id") == sprint_id)[
            "total_sp"
        ]
        sprint_total_sp = sprint_total_sp[0] if not sprint_total_sp.is_empty() else 0.0

        sprint_activations = activations_with_sp.filter(
            pl.col("sprint_id") == sprint_id
        )

        current_date = start_date
        cumulative_activated = 0.0
        while current_date <= end_date:
            activated_today = sprint_activations.filter(
                pl.col("activation_date") == current_date
            )["story_points"].sum()
            cumulative_activated += activated_today or 0.0

            pct = (
                (cumulative_activated / sprint_total_sp * 100)
                if sprint_total_sp > 0
                else 0.0
            )
            pct = min(100.0, max(0.0, pct))

            all_rows.append(
                {
                    "project_id": sprint["project_id"],
                    "iteration_id": sprint["id"],
                    "time_date": current_date,
                    "activation_pct": pct,
                }
            )
            current_date += timedelta(days=1)

    if not all_rows:
        return pl.DataFrame(
            schema={
                "project_id": pl.Utf8,
                "iteration_id": pl.Utf8,
                "time_date": pl.Date,
                "activation_pct": pl.Float64,
            }
        )

    return pl.DataFrame(all_rows)


def calculate_field_value_sprint_pct(
    sprints_df: pl.DataFrame,
    sprint_issues_df: pl.DataFrame,
    issues_df: pl.DataFrame,
    field_name: str,
    field_value: str,
    field_values_df: pl.DataFrame,
    field_keys_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Percentage of issues in sprint with specific field value.
    """
    # Resolve field_key_id
    field_key = field_keys_df.filter(
        pl.col("name").str.to_lowercase() == field_name.lower()
    )
    if field_key.is_empty():
        return sprints_df.select(
            ["project_id", pl.col("id").alias("iteration_id"), "start_date"]
        ).with_columns(pl.lit(0.0).alias("field_pct"))

    field_key_id = field_key["id"][0]

    # Get all issues in sprints
    sprint_full = sprint_issues_df.join(
        field_values_df.filter(pl.col("field_key_id") == field_key_id),
        on="issue_id",
        how="left",
    )

    # Calculate pct per sprint
    agg = (
        sprint_full.group_by("sprint_id")
        .agg(
            [
                pl.col("issue_id").count().alias("total_count"),
                pl.col("json_value")
                .filter(
                    pl.col("json_value").cast(pl.Utf8).str.to_lowercase()
                    == field_value.lower()
                )
                .count()
                .alias("match_count"),
            ]
        )
        .with_columns(
            (
                pl.when(pl.col("total_count") > 0)
                .then(pl.col("match_count") / pl.col("total_count") * 100)
                .otherwise(pl.lit(0.0))
            ).alias("field_pct")
        )
    )

    result = (
        sprints_df.select(
            ["project_id", pl.col("id").alias("iteration_id"), "start_date"]
        )
        .join(agg, left_on="iteration_id", right_on="sprint_id", how="left")
        .with_columns(pl.col("field_pct").fill_null(0.0))
    )

    return result


def calculate_unestimated_closed(
    sprints_df: pl.DataFrame,
    sprint_issues_df: pl.DataFrame,
    sprint_changelog_df: pl.DataFrame,
    issues_df: pl.DataFrame,
    issue_status_changelog_df: pl.DataFrame,
    done_status_ids: List[str],
    field_values_df: pl.DataFrame,
    sp_field_key_id: str,
) -> pl.DataFrame:
    """
    Count of closed issues without estimation.
    """
    # Get issues in done status at end of sprint
    done_status_ids_low = [s.lower() for s in done_status_ids]
    final_scope = identify_sprint_final_scope(
        sprint_issues_df, sprint_changelog_df, issues_df
    )
    completed = identify_completed_issues(
        final_scope,
        issues_df,
        issue_status_changelog_df,
        done_status_ids_low,
        sprints_df,
    )

    # Join with SP values
    unestimated = completed.join(
        field_values_df.filter(pl.col("field_key_id") == sp_field_key_id),
        on="issue_id",
        how="left",
    ).filter(
        pl.col("json_value").is_null()
        | (pl.col("json_value").cast(pl.Utf8) == "0")
        | (pl.col("json_value").cast(pl.Utf8) == "0.0")
    )

    agg = unestimated.group_by("sprint_id").agg(
        pl.col("issue_id").count().alias("unestimated_count")
    )

    result = (
        sprints_df.select(
            ["project_id", pl.col("id").alias("iteration_id"), "start_date"]
        )
        .join(agg, left_on="iteration_id", right_on="sprint_id", how="left")
        .with_columns(pl.col("unestimated_count").fill_null(0))
    )

    return result
