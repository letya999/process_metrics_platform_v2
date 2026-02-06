"""
Velocity Metrics Calculation (Python/Polars Implementation)

This module contains the business logic for calculating Sprint Velocity metrics.
It replaces the complex SQL Materialized View logic with debuggable Python code.

Key Metrics:
- Planned Issues: Issues remaining in the sprint at the moment of closing (Final Scope).
- Completed Issues: Issues from the Final Scope that were "Done" by sprint end.
- Story Points: Sum of story points for planned/completed issues (at sprint end).

Business Rules (User Defined):
1. **Plan (Commitment)**: All issues that were added to the sprint and NOT removed.
   - We look at the "Final State" of the sprint.
   - If an issue was added mid-sprint and stayed, it IS Planned.
   - If an issue was removed, it is NOT Planned.
2. **Fact (Completed)**: Any issue from the "Plan" that reached "Done" status by sprint end.
3. **Story Points**: Values are taken as of the Sprint End Date (Snapshot).
"""

from typing import List

import polars as pl


def get_done_status_ids(
    boards_df: pl.DataFrame, board_columns_df: pl.DataFrame
) -> List[str]:
    """
    Identify status IDs that represent "Done" based on board column configuration.
    """
    if board_columns_df.is_empty():
        return []

    done_columns = board_columns_df.filter(
        pl.col("name").str.to_lowercase().str.contains("done")
    )

    if "status_id" in done_columns.columns:
        return done_columns["status_id"].unique().to_list()

    return []


def identify_sprint_scope_at_close(
    sprint_issues_df: pl.DataFrame,
    sprint_changelog_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Determine the "Final Scope" of each sprint.
    Reflects the User's definition of "Plan":
    "All tasks that were added to sprint and not removed from it."

    Logic:
    1. Look at sprint_changelog_df.
    2. Find the LAST action for every (issue_id, sprint_id) pair.
    3. If Last Action == 'added' -> In Scope.
    4. If Last Action == 'removed' -> Out of Scope.
    5. If no history -> Fallback to sprint_issues_df (current membership).
    """
    # 1. Get dictionary of ALL potential pairs
    candidates = sprint_issues_df.select(["issue_id", "sprint_id"])

    if not sprint_changelog_df.is_empty():
        history_candidates = sprint_changelog_df.select(
            ["issue_id", "sprint_id"]
        ).unique()
        candidates = pl.concat([candidates, history_candidates]).unique()

    # 2. Determine final state from Changelog
    if (
        not sprint_changelog_df.is_empty()
        and "changed_at" in sprint_changelog_df.columns
    ):
        # Sort by time desc, take first (latest) action
        last_actions = (
            sprint_changelog_df.sort("changed_at", descending=True)
            .unique(subset=["issue_id", "sprint_id"], keep="first")
            .select(["issue_id", "sprint_id", pl.col("action").alias("last_action")])
        )

        # 3. Join candidates with last actions
        state = candidates.join(last_actions, on=["issue_id", "sprint_id"], how="left")
    else:
        state = candidates.with_columns(pl.lit(None).alias("last_action"))

    # 4. Check current membership (fallback)
    current_members = sprint_issues_df.with_columns(pl.lit(True).alias("is_current"))

    state_with_curr = state.join(
        current_members.select(["issue_id", "sprint_id", "is_current"]),
        on=["issue_id", "sprint_id"],
        how="left",
    )

    # 5. Apply Logic
    # If last_action is present: 'added' -> True, 'removed' -> False.
    # If last_action is missing (historical gap?): Fallback to is_current.

    planned = state_with_curr.with_columns(
        pl.when(pl.col("last_action") == "added")
        .then(True)
        .when(pl.col("last_action") == "removed")
        .then(False)
        .when(pl.col("last_action").is_null())
        .then(pl.col("is_current").fill_null(False))  # Fallback
        .otherwise(False)
        .alias("is_planned")
    )

    return planned.filter(pl.col("is_planned")).select(
        ["issue_id", "sprint_id", "is_planned"]
    )


def extract_story_points_at_end(
    candidates_df: pl.DataFrame,
    field_values_df: pl.DataFrame,
    field_keys_df: pl.DataFrame,
    field_value_changelog_df: pl.DataFrame,
    sprints_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Extract Story Points based on values at the Sprint End Date (Effective).
    Used for both Plan and Fact.
    """
    output_alias = "story_points"

    if field_keys_df.is_empty():
        return candidates_df.select(["issue_id", "sprint_id"]).with_columns(
            pl.lit(0.0).alias(output_alias)
        )

    # Identify SP fields
    sp_fields = field_keys_df.filter(
        (pl.col("external_key").is_in(["customfield_10036", "story_points"]))
        | (pl.col("name").str.to_lowercase().str.contains("story point"))
    )

    if sp_fields.is_empty():
        return candidates_df.select(["issue_id", "sprint_id"]).with_columns(
            pl.lit(0.0).alias(output_alias)
        )

    # Calculate effective end date
    dates_df = (
        sprints_df.select(["id", "end_date", "complete_date"])
        .with_columns(
            pl.coalesce(["complete_date", "end_date"]).alias("effective_end_date")
        )
        .select(["id", "effective_end_date"])
    )

    candidates_with_dates = candidates_df.join(
        dates_df,
        left_on="sprint_id",
        right_on="id",
        how="left",
    )

    sp_field_ids = sp_fields.select("id").to_series().to_list()

    # Historical lookup
    if not field_value_changelog_df.is_empty() and sp_field_ids:
        sp_changelog = field_value_changelog_df.filter(
            pl.col("field_key_id").is_in(sp_field_ids)
        )

        historical_sp = (
            candidates_with_dates.join(sp_changelog, on="issue_id", how="left")
            .filter(
                pl.col("changed_at").is_null()
                | (pl.col("changed_at") <= pl.col("effective_end_date"))
            )
            .sort("changed_at", descending=True)
            .unique(subset=["issue_id", "sprint_id"], keep="first")
            .with_columns(
                [
                    pl.when(pl.col("new_value").is_not_null())
                    .then(
                        pl.col("new_value")
                        .cast(pl.Utf8)
                        .str.strip_chars('"')
                        .cast(pl.Float64, strict=False)
                    )
                    .otherwise(0.0)
                    .alias(output_alias)
                ]
            )
            .select(["issue_id", "sprint_id", output_alias])
        )
    else:
        historical_sp = pl.DataFrame()

    # Fallback to current values
    if historical_sp.is_empty():
        current_sp = (
            candidates_df.join(field_values_df, on="issue_id", how="left")
            .join(sp_fields, left_on="field_key_id", right_on="id", how="inner")
            .with_columns(
                [
                    pl.when(pl.col("json_value").is_not_null())
                    .then(
                        pl.col("json_value")
                        .str.strip_chars('"')
                        .cast(pl.Float64, strict=False)
                    )
                    .otherwise(0.0)
                    .alias(output_alias)
                ]
            )
            .select(["issue_id", "sprint_id", output_alias])
            .group_by(["issue_id", "sprint_id"])
            .agg(pl.col(output_alias).max())
        )
        sp_values = current_sp
    else:
        sp_values = historical_sp

    result = candidates_df.select(["issue_id", "sprint_id"]).join(
        sp_values, on=["issue_id", "sprint_id"], how="left"
    )

    return result.with_columns(pl.col(output_alias).fill_null(0.0))


def identify_completed_subset(
    scope_df: pl.DataFrame,
    issues_df: pl.DataFrame,
    status_changelog_df: pl.DataFrame,
    done_status_ids: List[str],
    sprints_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Filter the Scope (Plan) to find what was Completed.
    User Definition: "FACT - all tasks from plan, that are in done"

    Implementation:
    Check if issue was 'Done' at the time of sprint completion.
    """
    sprint_dates = sprints_df.select(["id", "complete_date", "end_date"])

    with_dates = scope_df.join(
        sprint_dates,
        left_on="sprint_id",
        right_on="id",
        how="left",
    ).with_columns(
        [pl.coalesce(["complete_date", "end_date"]).alias("effective_end_date")]
    )

    # Check 1: Effective Resolved Date <= Sprint End
    resolved_in_time = (
        with_dates.join(
            issues_df.select(["id", "jira_resolved_at", "status_id"]),
            left_on="issue_id",
            right_on="id",
            how="left",
        )
        .filter(
            pl.col("jira_resolved_at").is_not_null()
            & (pl.col("jira_resolved_at") <= pl.col("effective_end_date"))
            & (pl.col("status_id").is_in(done_status_ids))
        )
        .select(["issue_id", "sprint_id"])
        .with_columns(pl.lit(True).alias("is_completed"))
    )

    # Check 2: Changelog History (Moved to Done <= Sprint End)
    if not status_changelog_df.is_empty() and done_status_ids:
        done_by_changelog = (
            with_dates.join(status_changelog_df, on="issue_id", how="left")
            .filter(
                pl.col("to_status_id").is_in(done_status_ids)
                & (pl.col("changed_at") <= pl.col("effective_end_date"))
            )
            .select(["issue_id", "sprint_id"])
            .unique()
            .with_columns(pl.lit(True).alias("is_completed"))
        )
        completed = pl.concat([resolved_in_time, done_by_changelog]).unique()
    else:
        completed = resolved_in_time

    return completed


def calculate_velocity_facts(
    sprints_df: pl.DataFrame,
    sprint_issues_df: pl.DataFrame,
    sprint_changelog_df: pl.DataFrame,
    issues_df: pl.DataFrame,
    field_values_df: pl.DataFrame,
    field_keys_df: pl.DataFrame,
    status_changelog_df: pl.DataFrame,
    boards_df: pl.DataFrame,
    board_columns_df: pl.DataFrame,
    field_value_changelog_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Main orchestration function: Calculate Velocity facts.
    """
    done_status_ids = get_done_status_ids(boards_df, board_columns_df)

    # 1. Identify "Plan" (Total Final Scope)
    scope = identify_sprint_scope_at_close(sprint_issues_df, sprint_changelog_df)

    # 2. Identify "Fact" (Completed Subset of Plan)
    completed_flags = identify_completed_subset(
        scope, issues_df, status_changelog_df, done_status_ids, sprints_df
    )

    # 3. Extract Story Points (Using values at Sprint End)
    sp_vals = extract_story_points_at_end(
        scope, field_values_df, field_keys_df, field_value_changelog_df, sprints_df
    )

    # 4. Combine Facts
    # scope has [issue_id, sprint_id, is_planned=True]
    facts = (
        scope.join(completed_flags, on=["issue_id", "sprint_id"], how="left")
        .join(sp_vals, on=["issue_id", "sprint_id"], how="left")
        .with_columns(
            [
                pl.col("is_completed").fill_null(False),
                pl.col("story_points").fill_null(0.0),
            ]
        )
    )

    # 5. Aggregate by Sprint
    # Planned = Sum of SP of all issues in Scope
    # Completed = Sum of SP of all issues in Scope that are Completed

    agg = facts.group_by("sprint_id").agg(
        [
            pl.count("issue_id").alias("planned_issues"),
            pl.sum("story_points").alias("planned_story_points"),
            pl.col("issue_id")
            .filter(pl.col("is_completed"))
            .count()
            .alias("completed_issues"),
            pl.col("story_points")
            .filter(pl.col("is_completed"))
            .sum()
            .alias("completed_story_points"),
        ]
    )

    # 6. Join with Sprint Details and Deduplicate
    raw_metrics = sprints_df.join(
        agg, left_on="id", right_on="sprint_id", how="left"
    ).with_columns(
        [
            pl.col("planned_issues").fill_null(0),
            pl.col("planned_story_points").fill_null(0.0),
            pl.col("completed_issues").fill_null(0),
            pl.col("completed_story_points").fill_null(0.0),
        ]
    )

    # Deduplicate: Group by Project and Sprint Name
    final_metrics = (
        raw_metrics.group_by(["project_id", "name"])
        .agg(
            [
                pl.col("planned_issues").sum(),
                pl.col("planned_story_points").sum(),
                pl.col("completed_issues").sum(),
                pl.col("completed_story_points").sum(),
                pl.col("start_date").min(),
                pl.col("end_date").max(),
                pl.col("id").first().alias("iteration_id"),
            ]
        )
        .rename({"name": "iteration_name"})
        .select(
            [
                "project_id",
                "iteration_id",
                "iteration_name",
                "start_date",
                "end_date",
                "planned_story_points",
                "completed_story_points",
                "planned_issues",
                "completed_issues",
            ]
        )
    )

    return final_metrics


def calculate_velocity_slice_by_issue_type(
    sprint_issues_df: pl.DataFrame,
    sprint_changelog_df: pl.DataFrame,
    issues_df: pl.DataFrame,
    sprints_df: pl.DataFrame,
    field_values_df: pl.DataFrame,
    field_keys_df: pl.DataFrame,
    status_changelog_df: pl.DataFrame,
    boards_df: pl.DataFrame,
    board_columns_df: pl.DataFrame,
    field_value_changelog_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Calculate Velocity sliced by Issue Type.
    """
    done_status_ids = get_done_status_ids(boards_df, board_columns_df)

    scope = identify_sprint_scope_at_close(sprint_issues_df, sprint_changelog_df)

    # Join issue type
    scope_with_type = scope.join(
        issues_df.select(["id", "type_name"]),
        left_on="issue_id",
        right_on="id",
        how="left",
    )

    completed_flags = identify_completed_subset(
        scope, issues_df, status_changelog_df, done_status_ids, sprints_df
    )

    sp_vals = extract_story_points_at_end(
        scope, field_values_df, field_keys_df, field_value_changelog_df, sprints_df
    )

    facts = (
        scope_with_type.join(completed_flags, on=["issue_id", "sprint_id"], how="left")
        .join(sp_vals, on=["issue_id", "sprint_id"], how="left")
        .with_columns(
            [
                pl.col("is_completed").fill_null(False),
                pl.col("story_points").fill_null(0.0),
            ]
        )
    )

    agg = facts.group_by(["sprint_id", "type_name"]).agg(
        [
            pl.count("issue_id").alias("planned_issues"),
            pl.sum("story_points").alias("planned_story_points"),
            pl.col("issue_id")
            .filter(pl.col("is_completed"))
            .count()
            .alias("completed_issues"),
            pl.col("story_points")
            .filter(pl.col("is_completed"))
            .sum()
            .alias("completed_story_points"),
        ]
    )

    raw_metrics = sprints_df.join(
        agg, left_on="id", right_on="sprint_id", how="left"
    ).with_columns(
        [
            pl.col("planned_issues").fill_null(0),
            pl.col("planned_story_points").fill_null(0.0),
            pl.col("completed_issues").fill_null(0),
            pl.col("completed_story_points").fill_null(0.0),
        ]
    )

    final_metrics = (
        raw_metrics.group_by(["project_id", "name", "type_name"])
        .agg(
            [
                pl.col("planned_issues").sum(),
                pl.col("planned_story_points").sum(),
                pl.col("completed_issues").sum(),
                pl.col("completed_story_points").sum(),
                pl.col("start_date").min(),
                pl.col("end_date").max(),
                pl.col("id").first().alias("iteration_id"),
            ]
        )
        .rename({"name": "iteration_name", "type_name": "issue_type"})
        .select(
            [
                "project_id",
                "iteration_id",
                "iteration_name",
                "start_date",
                "end_date",
                "issue_type",
                "planned_story_points",
                "completed_story_points",
                "planned_issues",
                "completed_issues",
            ]
        )
    )

    return final_metrics
