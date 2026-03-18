"""
Velocity Metrics Calculation (Python/Polars Implementation)

This module contains the business logic for calculating Sprint Velocity metrics.
It replaces the complex SQL Materialized View logic with debuggable Python code.

JIRA Sprint Report Definitions (based on actual Jira behavior):
=================================================================

1. **COMMITMENT (Plan)**:
   - Issues that were in the sprint at START time
   - Story Points value at sprint START
   - EXCLUDES issues that were REMOVED from sprint later
   - The formula: Commitment = (Issues at start) - (Issues removed after start)

2. **COMPLETED (Fact)**:
   - ALL issues that reached "Done" status by sprint end
   - INCLUDING scope creep (issues added after start)
   - Story Points value at sprint END

3. **Story Points**:
   - We use CURRENT story points as we don't have reliable historical SP data
   - This matches most practical use cases
"""

from typing import List

import polars as pl


def get_done_status_ids(
    boards_df: pl.DataFrame,
    board_columns_df: pl.DataFrame,
    issue_statuses_df: pl.DataFrame = None,
) -> List[str]:
    """
    Identify status IDs that represent "Done".
    Priority:
    1. Status Category = 'done' (from issue_statuses).
    2. Column Name contains 'done' (fallback).
    """
    if issue_statuses_df is None:
        issue_statuses_df = pl.DataFrame()
    done_ids = []

    # 1. Status Category
    if not issue_statuses_df.is_empty() and "category" in issue_statuses_df.columns:
        cat_done = issue_statuses_df.filter(
            pl.col("category").str.to_lowercase() == "done"
        )
        if "id" in cat_done.columns:
            ids = cat_done["id"].cast(pl.Utf8).str.to_lowercase().unique().to_list()
            done_ids.extend(ids)

    # 2. Board Columns (Fallback or Additive)
    if not board_columns_df.is_empty():
        done_columns = board_columns_df.filter(
            pl.col("name").str.to_lowercase().str.contains("done")
        )
        if "status_id" in done_columns.columns:
            ids = (
                done_columns["status_id"]
                .cast(pl.Utf8)
                .str.to_lowercase()
                .unique()
                .to_list()
            )
            done_ids.extend(ids)

    return list(set(done_ids))


GRACE_PERIOD_MINUTES = 0


def identify_sprint_final_scope(
    sprint_issues_df: pl.DataFrame,
    sprint_changelog_df: pl.DataFrame,
    issues_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Determine the "Final Scope" of each sprint at closure.

    Logic:
    1. Primary source: sprint_changelog_df. If an issue's last action in sprint
       is 'added', it's in the final scope.
    2. Fallback: sprint_issues_df. Issues listed here are assumed in scope
       if they have no changelog.
    3. Filter: Always exclude Sub-tasks using issues_df.

    Returns DataFrame with columns: [issue_id, sprint_id]
    """
    # 1. Get non-sub-task issue IDs
    non_sub_ids = (
        issues_df.filter(
            ~pl.col("type_name").cast(pl.Utf8).str.to_lowercase().str.contains("sub")
        )
        .select(["id"])
        .rename({"id": "issue_id"})
    )

    if sprint_changelog_df.is_empty():
        # Just use sprint_issues_df filtered by non-sub
        return (
            sprint_issues_df.join(non_sub_ids, on="issue_id", how="inner")
            .select(["issue_id", "sprint_id"])
            .unique()
        )

    # 2. Extract scope from changelog
    last_actions = sprint_changelog_df.sort("changed_at", descending=True).unique(
        subset=["issue_id", "sprint_id"], keep="first"
    )

    changelog_scope = last_actions.filter(pl.col("action") == "added").select(
        ["issue_id", "sprint_id"]
    )

    # 3. Fallback for issues in sprint_issues with NO changelog
    has_cl = last_actions.select(["issue_id", "sprint_id"]).unique()
    fallback_scope = sprint_issues_df.join(
        has_cl, on=["issue_id", "sprint_id"], how="anti"
    ).select(["issue_id", "sprint_id"])

    # 4. Combine and filter by non-sub-task
    final_scope = (
        pl.concat([changelog_scope, fallback_scope])
        .unique()
        .join(non_sub_ids, on="issue_id", how="inner")
    )

    return final_scope


def identify_sprint_commitment(
    sprint_changelog_df: pl.DataFrame,
    sprints_df: pl.DataFrame,
    issues_df: pl.DataFrame,
    sprint_issues_df: pl.DataFrame = None,
) -> pl.DataFrame:
    """
    Identify Sprint Commitment (Issues in sprint at Start Date + Grace Period).

    Logic:
    1. Find issues that were in the sprint at (start_date + GRACE_PERIOD_MINUTES).
    2. "In sprint" means: they were added before/at the cutoff AND not removed before/at the cutoff.
    3. Filter: Jira excludes issues that are LATER removed from the sprint from Commitment.
       So we also check that their FINAL action in the sprint is 'added'.
    4. Fallback: Issues in sprint_issues_df with no changelog are assumed commitment.

    Returns DataFrame with columns: [issue_id, sprint_id]
    """
    # 1. Get non-sub-task issue IDs
    if "jira_created_at" in issues_df.columns:
        non_sub_ids = (
            issues_df.filter(
                ~pl.col("type_name")
                .cast(pl.Utf8)
                .str.to_lowercase()
                .str.contains("sub")
            )
            .select(["id", "jira_created_at"])
            .rename({"id": "issue_id"})
        )
    else:
        non_sub_ids = (
            issues_df.filter(
                ~pl.col("type_name")
                .cast(pl.Utf8)
                .str.to_lowercase()
                .str.contains("sub")
            )
            .select(["id"])
            .rename({"id": "issue_id"})
            .with_columns(pl.lit(None).alias("jira_created_at"))
        )

    # Get sprint start dates + grace period
    sprint_dates = sprints_df.select(
        [
            "id",
            "start_date",
            (pl.col("start_date") + pl.duration(minutes=GRACE_PERIOD_MINUTES)).alias(
                "cutoff_date"
            ),
        ]
    ).filter(pl.col("start_date").is_not_null())

    if sprint_changelog_df.is_empty():
        if sprint_issues_df is not None:
            return (
                sprint_issues_df.join(non_sub_ids, on="issue_id", how="inner")
                .select(["issue_id", "sprint_id"])
                .unique()
            )
        return pl.DataFrame(schema={"issue_id": pl.Utf8, "sprint_id": pl.Utf8})

    # 2. Find issues present at cutoff
    # To be in commitment, an issue must have been added before cutoff and not removed before cutoff
    # Alternatively, just check the status at cutoff time
    cl_with_dates = sprint_changelog_df.join(
        sprint_dates, left_on="sprint_id", right_on="id", how="inner"
    )

    status_at_cutoff = (
        cl_with_dates.filter(pl.col("changed_at") <= pl.col("cutoff_date"))
        .sort("changed_at", descending=True)
        .unique(subset=["issue_id", "sprint_id"], keep="first")
        .filter(pl.col("action") == "added")
        .select(["issue_id", "sprint_id"])
    )

    # 3. Use strict snapshot (no lookahead for removed issues)
    # This aligns best with Jira's definition of Commitment (Plan).
    commitment_cl = status_at_cutoff

    # 4. Fallback for issues without changelog
    if sprint_issues_df is not None:
        has_cl = sprint_changelog_df.select(["issue_id", "sprint_id"]).unique()
        fallback_commitment = sprint_issues_df.join(
            has_cl, on=["issue_id", "sprint_id"], how="anti"
        ).select(["issue_id", "sprint_id"])

        commitment = pl.concat([commitment_cl, fallback_commitment]).unique()
    else:
        commitment = commitment_cl

    # 5. Handle "Ghost" Issues (Removed but never Added)
    # If an issue created BEFORE sprint start is removed AFTER sprint start,
    # and has NO added event, it was implicitly in the sprint at start.
    if not sprint_changelog_df.is_empty():
        # Get all removals
        removals = (
            cl_with_dates.filter(pl.col("action") == "removed")
            .select(["issue_id", "sprint_id", "start_date"])
            .unique()
        )

        # Check against existing commitment
        missing_adds = removals.join(
            commitment, on=["issue_id", "sprint_id"], how="anti"
        )

        if not missing_adds.is_empty():
            # Check creation dates
            # Use non_sub_ids which has (issue_id, jira_created_at) and filters subtasks
            inferred = (
                missing_adds.join(non_sub_ids, on="issue_id", how="inner")
                .filter(pl.col("jira_created_at") < pl.col("start_date"))
                .select(["issue_id", "sprint_id"])
            )
            commitment = pl.concat([commitment, inferred]).unique()

    # 6. Filter by non-sub
    commitment = commitment.join(non_sub_ids, on="issue_id", how="inner")

    return commitment


def determine_story_points_at_date(
    scope_df: pl.DataFrame,  # [issue_id, sprint_id]
    sprints_df: pl.DataFrame,
    current_sp_df: pl.DataFrame,
    changelog_df: pl.DataFrame,
    field_keys_df: pl.DataFrame,
    date_col: str = "start_date",
) -> pl.DataFrame:
    """
    Determine Story Points for each issue in scope at the specific sprint date.
    """
    # Get target dates
    target_dates = sprints_df.select(["id", date_col]).rename(
        {"id": "sprint_id", date_col: "target_date"}
    )

    scope_with_dates = scope_df.join(target_dates, on="sprint_id", how="left")

    # Identify SP fields
    sp_fields = field_keys_df.filter(
        (
            pl.col("external_key").is_in(
                ["customfield_10036", "customfield_10016", "story_points"]
            )
        )
        | (pl.col("name").str.to_lowercase().str.contains("story point"))
    )
    if sp_fields.is_empty() or changelog_df.is_empty():
        return scope_df.join(current_sp_df, on="issue_id", how="left").select(
            ["issue_id", "sprint_id", "story_points"]
        )

    sp_field_ids = sp_fields["id"].to_list()

    # Filter changelog
    changes = changelog_df.filter(pl.col("field_key_id").is_in(sp_field_ids))

    # Join scope with changes
    # We want changes where changed_at > target_date
    # Since we can't inequality join easily in eager/lazy mix, we might need to join then filter

    # Optimization: Filter changes to relevant issues first
    relevant_issues = scope_df.select("issue_id").unique()
    changes_filtered = changes.join(relevant_issues, on="issue_id", how="inner")

    joined = scope_with_dates.join(changes_filtered, on="issue_id", how="left")

    # Find corrections: First change AFTER target_date
    corrections = (
        joined.filter(
            pl.col("changed_at").is_not_null()
            & (pl.col("changed_at") > pl.col("target_date"))
        )
        .sort("changed_at", descending=False)  # Ascending
        .unique(subset=["issue_id", "sprint_id"], keep="first")
        .select(["issue_id", "sprint_id", "old_value"])
    )

    # Parse old_value
    corrections = corrections.with_columns(
        [
            pl.when(
                pl.col("old_value").is_not_null()
                & pl.col("old_value")
                .cast(pl.Utf8)
                .str.strip_chars()
                .str.contains(r"^-?[0-9]+\.?[0-9]*$")
            )
            .then(
                pl.col("old_value")
                .cast(pl.Utf8)
                .str.strip_chars()
                .cast(pl.Float64, strict=False)
            )
            .otherwise(0.0)
            .alias("historic_sp")
        ]
    )

    # Join back to full scope
    init_sp = scope_df.join(current_sp_df, on="issue_id", how="left")

    final = (
        init_sp.join(corrections, on=["issue_id", "sprint_id"], how="left")
        .with_columns(
            pl.coalesce(["historic_sp", "story_points"])
            .fill_null(0.0)
            .alias("story_points")
        )
        .select(["issue_id", "sprint_id", "story_points"])
    )

    return final


def extract_story_points(
    issues_df: pl.DataFrame,
    field_values_df: pl.DataFrame,
    field_keys_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Extract Story Points for each issue.

    Returns DataFrame with columns: [issue_id, story_points]

    Note: This uses CURRENT story point values. For historical accuracy,
    we would need field_value_changelog, but that adds complexity and
    often has incomplete data.
    """
    # Identify SP field keys
    if field_keys_df.is_empty():
        return pl.DataFrame(schema={"issue_id": pl.Utf8, "story_points": pl.Float64})

    sp_fields = field_keys_df.filter(
        (
            pl.col("external_key").is_in(
                ["customfield_10036", "customfield_10016", "story_points"]
            )
        )
        | (pl.col("name").str.to_lowercase().str.contains("story point"))
    )

    if sp_fields.is_empty():
        return (
            issues_df.select(["id"])
            .rename({"id": "issue_id"})
            .with_columns(pl.lit(0.0).alias("story_points"))
        )

    sp_field_ids = sp_fields.select("id").to_series().to_list()

    # Filter field_values to only SP fields
    sp_values = field_values_df.filter(pl.col("field_key_id").is_in(sp_field_ids))

    if sp_values.is_empty():
        return (
            issues_df.select(["id"])
            .rename({"id": "issue_id"})
            .with_columns(pl.lit(0.0).alias("story_points"))
        )

    # Parse SP values, taking MAX per issue (in case multiple SP fields)
    sp_parsed = (
        sp_values.with_columns(
            [
                pl.when(
                    pl.col("json_value").is_not_null()
                    & pl.col("json_value")
                    .cast(pl.Utf8)
                    .str.strip_chars()
                    .str.contains(r"^-?[0-9]+\.?[0-9]*$")
                )
                .then(
                    pl.col("json_value")
                    .cast(pl.Utf8)
                    .str.strip_chars()
                    .cast(pl.Float64, strict=False)
                )
                .otherwise(0.0)
                .alias("sp_value")
            ]
        )
        .group_by("issue_id")
        .agg(pl.col("sp_value").max().alias("story_points"))
    )

    # Ensure all issues have SP (default 0)
    all_issues = issues_df.select(["id"]).rename({"id": "issue_id"})
    result = all_issues.join(sp_parsed, on="issue_id", how="left").with_columns(
        pl.col("story_points").fill_null(0.0)
    )

    return result


def identify_completed_issues(
    scope_df: pl.DataFrame,
    issues_df: pl.DataFrame,
    status_changelog_df: pl.DataFrame,
    done_status_ids: List[str],
    sprints_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Identify issues from scope that were "Done" by sprint end.

    Logic:
    1. Check status_changelog for the status at sprint end time.
    2. If status at end is in done_status_ids -> completed.
    3. Fallback: if no status changelog, check current status.

    Returns DataFrame with columns: [issue_id, sprint_id, is_completed]
    """
    sprint_dates = sprints_df.select(
        ["id", pl.coalesce(["complete_date", "end_date"]).alias("effective_end_date")]
    )

    scope_with_dates = scope_df.join(
        sprint_dates, left_on="sprint_id", right_on="id", how="left"
    )

    if status_changelog_df.is_empty() or not done_status_ids:
        # Fallback: use current status from issues_df
        return _identify_completed_by_current_status(
            scope_df, issues_df, done_status_ids
        )

    # Find the status at sprint end for each issue
    status_at_end = (
        scope_with_dates.join(status_changelog_df, on="issue_id", how="left")
        .filter(
            pl.col("changed_at").is_not_null()
            & (pl.col("changed_at") <= pl.col("effective_end_date"))
        )
        .sort("changed_at", descending=True)
        .unique(subset=["issue_id", "sprint_id"], keep="first")
        .select(["issue_id", "sprint_id", "to_status_id"])
    )

    # Check if status is "done"
    completed_from_changelog = status_at_end.filter(
        pl.col("to_status_id").cast(pl.Utf8).str.to_lowercase().is_in(done_status_ids)
    ).select(["issue_id", "sprint_id"])

    # Find issues without status changelog - need special handling
    has_changelog = status_at_end.select(["issue_id", "sprint_id"]).unique()
    no_changelog = scope_df.join(
        has_changelog, on=["issue_id", "sprint_id"], how="anti"
    )

    # 3. Handle issues with logs strictly AFTER effective_end_date
    # If an issue has logs but none before end_date, we should check the FIRST log after end_date.
    # The status BEFORE that change was the status at end_date.

    if not no_changelog.is_empty():
        # Get all issues in no_changelog that have SOME changelog (just after sprint end)
        scope_with_cl = no_changelog.join(
            scope_with_dates.select(["issue_id", "sprint_id", "effective_end_date"]),
            on=["issue_id", "sprint_id"],
            how="inner",
        ).join(
            status_changelog_df.select("issue_id").unique(), on="issue_id", how="inner"
        )

        if not scope_with_cl.is_empty():
            # Find first change AFTER effective_end_date
            future_changes = scope_with_cl.join(
                status_changelog_df, on="issue_id", how="left"
            ).filter(
                pl.col("changed_at").is_not_null()
                & (pl.col("changed_at") > pl.col("effective_end_date"))
            )

            if not future_changes.is_empty():
                first_future_change = (
                    future_changes.sort("changed_at", descending=False)  # Ascending
                    .unique(subset=["issue_id", "sprint_id"], keep="first")
                    .select(
                        ["issue_id", "sprint_id", "from_status_id"]
                    )  # status BEFORE the change
                )

                # Check if that status was "done"
                completed_future = first_future_change.filter(
                    pl.col("from_status_id")
                    .cast(pl.Utf8)
                    .str.to_lowercase()
                    .is_in(done_status_ids)
                ).select(["issue_id", "sprint_id"])

                # Exclude these from no_changelog (we handled them)
                no_changelog = no_changelog.join(
                    first_future_change.select(["issue_id", "sprint_id"]),
                    on=["issue_id", "sprint_id"],
                    how="anti",
                )

                completed = pl.concat(
                    [completed_from_changelog, completed_future]
                ).unique()
            else:
                completed = completed_from_changelog
        else:
            completed = completed_from_changelog

        # 4. Final fallback: use current status for remaining issues
        if not no_changelog.is_empty():
            fallback_completed = _identify_completed_by_current_status(
                no_changelog, issues_df, done_status_ids
            )
            completed = pl.concat([completed, fallback_completed]).unique()
    else:
        completed = completed_from_changelog

    return completed.with_columns(pl.lit(True).alias("is_completed"))


def _identify_completed_by_current_status(
    scope_df: pl.DataFrame,
    issues_df: pl.DataFrame,
    done_status_ids: List[str],
) -> pl.DataFrame:
    """Fallback: identify completed by current status."""
    issues_status = issues_df.select(["id", "status_id"]).rename({"id": "issue_id"})

    completed = (
        scope_df.join(issues_status, on="issue_id", how="left")
        .filter(
            pl.col("status_id").cast(pl.Utf8).str.to_lowercase().is_in(done_status_ids)
        )
        .select(["issue_id", "sprint_id"])
    )

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
    issue_statuses_df: pl.DataFrame = None,
) -> pl.DataFrame:
    """
    Main orchestration function: Calculate Velocity facts.

    Returns DataFrame with sprint-level velocity metrics.
    """
    if issue_statuses_df is None:
        issue_statuses_df = pl.DataFrame()
    done_status_ids = get_done_status_ids(
        boards_df, board_columns_df, issue_statuses_df
    )

    # 1. Extract CURRENT Story Points for all issues
    current_story_points_df = extract_story_points(
        issues_df, field_values_df, field_keys_df
    )

    # 2. Identify Commitment (Plan)
    commitment_df = identify_sprint_commitment(
        sprint_changelog_df, sprints_df, issues_df, sprint_issues_df
    )

    # 2b. Calculate Historical SP for Commitment (at Start Date)
    commitment_with_sp = determine_story_points_at_date(
        commitment_df,
        sprints_df,
        current_story_points_df,
        field_value_changelog_df,
        field_keys_df,
        date_col="start_date",
    )

    # 3. Identify Final Scope
    final_scope_df = identify_sprint_final_scope(
        sprint_issues_df, sprint_changelog_df, issues_df
    )

    # 4. Identify Completed
    completed_df = identify_completed_issues(
        final_scope_df, issues_df, status_changelog_df, done_status_ids, sprints_df
    )

    # 5. Calculate Historical SP for Completed (at End/Complete Date)
    # Use coalesce(complete_date, end_date) as the timestamp
    sprints_with_eff_end = sprints_df.with_columns(
        pl.coalesce(["complete_date", "end_date"]).alias("effective_end_date")
    )

    completed_with_sp = determine_story_points_at_date(
        completed_df.select(["issue_id", "sprint_id"]),
        sprints_with_eff_end,
        current_story_points_df,
        field_value_changelog_df,
        field_keys_df,
        date_col="effective_end_date",
    )

    # 6. Aggregate by Sprint
    plan_agg = commitment_with_sp.group_by("sprint_id").agg(
        [
            pl.col("issue_id").count().cast(pl.Int64).alias("planned_issues"),
            pl.col("story_points").sum().alias("planned_story_points"),
        ]
    )

    fact_agg = completed_with_sp.group_by("sprint_id").agg(
        [
            pl.col("issue_id").count().cast(pl.Int64).alias("completed_issues"),
            pl.col("story_points").sum().alias("completed_story_points"),
        ]
    )

    # 7. Join with Sprint Details
    result = (
        sprints_df.join(plan_agg, left_on="id", right_on="sprint_id", how="left")
        .join(fact_agg, left_on="id", right_on="sprint_id", how="left")
        .with_columns(
            [
                pl.col("planned_issues").fill_null(0),
                pl.col("planned_story_points").fill_null(0.0),
                pl.col("completed_issues").fill_null(0),
                pl.col("completed_story_points").fill_null(0.0),
            ]
        )
    )

    # 8. Deduplicate sprints with same name (merge metrics)
    final_metrics = (
        result.group_by(["project_id", "name"])
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
    issue_statuses_df: pl.DataFrame = None,
) -> pl.DataFrame:
    """
    Calculate Velocity sliced by Issue Type.
    """
    if issue_statuses_df is None:
        issue_statuses_df = pl.DataFrame()
    done_status_ids = get_done_status_ids(
        boards_df, board_columns_df, issue_statuses_df
    )

    # Extract Story Points
    current_story_points_df = extract_story_points(
        issues_df, field_values_df, field_keys_df
    )

    # Get issue types
    issue_types_df = issues_df.select(["id", "type_name"]).rename({"id": "issue_id"})

    # Commitment and Final Scope
    commitment_df = identify_sprint_commitment(
        sprint_changelog_df, sprints_df, issues_df, sprint_issues_df
    )
    final_scope_df = identify_sprint_final_scope(
        sprint_issues_df, sprint_changelog_df, issues_df
    )

    # Completed
    completed_df = identify_completed_issues(
        final_scope_df, issues_df, status_changelog_df, done_status_ids, sprints_df
    )

    # Historical SP
    commitment_with_sp = determine_story_points_at_date(
        commitment_df,
        sprints_df,
        current_story_points_df,
        field_value_changelog_df,
        field_keys_df,
        date_col="start_date",
    )

    sprints_with_eff_end = sprints_df.with_columns(
        pl.coalesce(["complete_date", "end_date"]).alias("effective_end_date")
    )

    completed_with_sp = determine_story_points_at_date(
        completed_df.select(["issue_id", "sprint_id"]),
        sprints_with_eff_end,
        current_story_points_df,
        field_value_changelog_df,
        field_keys_df,
        date_col="effective_end_date",
    )

    # Join with issue type and SP
    commitment_full = commitment_with_sp.join(
        issue_types_df, on="issue_id", how="left"
    ).with_columns(
        [
            pl.col("story_points").fill_null(0.0),
            pl.col("type_name").fill_null("Unknown"),
        ]
    )

    completed_full = completed_with_sp.join(
        issue_types_df, on="issue_id", how="left"
    ).with_columns(
        [
            pl.col("story_points").fill_null(0.0),
            pl.col("type_name").fill_null("Unknown"),
        ]
    )

    # Aggregate by Sprint and Type
    plan_agg = commitment_full.group_by(["sprint_id", "type_name"]).agg(
        [
            pl.col("issue_id").count().cast(pl.Int64).alias("planned_issues"),
            pl.col("story_points").sum().alias("planned_story_points"),
        ]
    )

    fact_agg = completed_full.group_by(["sprint_id", "type_name"]).agg(
        [
            pl.col("issue_id").count().cast(pl.Int64).alias("completed_issues"),
            pl.col("story_points").sum().alias("completed_story_points"),
        ]
    )

    # Combine plan and fact
    combined = plan_agg.join(
        fact_agg, on=["sprint_id", "type_name"], how="full", suffix="_fact"
    ).with_columns(
        [
            pl.col("planned_issues").fill_null(0),
            pl.col("planned_story_points").fill_null(0.0),
            pl.col("completed_issues").fill_null(0),
            pl.col("completed_story_points").fill_null(0.0),
        ]
    )

    # Join with Sprint Details
    result = sprints_df.join(combined, left_on="id", right_on="sprint_id", how="left")

    # Deduplicate
    final_metrics = (
        result.group_by(["project_id", "name", "type_name"])
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
        .with_columns(pl.col("issue_type").fill_null("Unknown"))
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
