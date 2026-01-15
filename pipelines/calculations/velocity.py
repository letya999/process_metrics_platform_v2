"""
Velocity Metrics Calculation (Python/Polars Implementation)

This module contains the business logic for calculating Sprint Velocity metrics.
It replaces the complex SQL Materialized View logic with debuggable Python code.

Key Metrics:
- Planned Issues: Issues in sprint at start
- Completed Issues: Issues marked as "Done" by sprint end
- Story Points: Sum of story points for planned/completed issues

Business Rules:
1. Issue is "Planned" if it was added to sprint BEFORE sprint start
2. Issue is "Completed" if it reached "Done" status by sprint end
3. Story Points are extracted from custom fields with fallbacks
"""

from typing import List

import polars as pl


def get_done_status_ids(
    boards_df: pl.DataFrame, board_columns_df: pl.DataFrame
) -> List[str]:
    """
    Identify status IDs that represent "Done" based on board column configuration.

    Logic: Find columns with names containing "done" (case-insensitive)
    and extract their associated status IDs.

    Args:
        boards_df: DataFrame of boards
        board_columns_df: DataFrame of board columns (should include status_id column)

    Returns:
        List of status IDs representing "Done" state

    Example:
        >>> done_ids = get_done_status_ids(boards_df, columns_df)
        >>> print(done_ids)
        ['10001', '10002']
    """
    if board_columns_df.is_empty():
        return []

    done_columns = board_columns_df.filter(
        pl.col("name").str.to_lowercase().str.contains("done")
    )

    if "status_id" in done_columns.columns:
        return done_columns["status_id"].unique().to_list()

    return []


def identify_planned_issues(
    sprint_issues_df: pl.DataFrame,
    sprint_changelog_df: pl.DataFrame,
    issues_df: pl.DataFrame,
    sprints_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Determine which issues were "Planned" at sprint start.

    Business Rules:
    1. If issue was explicitly added BEFORE sprint start → Planned
    2. If issue was created BEFORE sprint start AND never removed → Planned
    3. If issue was added MID-sprint → NOT Planned (scope creep)

    Args:
        sprint_issues_df: Current sprint-issue membership
        sprint_changelog_df: History of sprint membership changes
        issues_df: Issue details (including created_at)
        sprints_df: Sprint details (including start_date)

    Returns:
        DataFrame with columns: [issue_id, sprint_id, is_planned]

    Example:
        >>> planned = identify_planned_issues(sprint_issues, changelog, issues, sprints)
        >>> print(planned.filter(pl.col("is_planned")).shape)
        (150, 3)  # 150 planned issues
    """
    # Step 1: Join sprint_issues with sprints to get start_date
    membership = sprint_issues_df.join(
        sprints_df.select(["id", "start_date"]),
        left_on="sprint_id",
        right_on="id",
        how="left",
    )

    # Step 2: For each (issue, sprint), find LAST action <= start_date
    # This tells us the state of the issue at sprint start
    if (
        not sprint_changelog_df.is_empty()
        and "changed_at" in sprint_changelog_df.columns
    ):
        state_at_start = (
            membership.join(
                sprint_changelog_df, on=["issue_id", "sprint_id"], how="left"
            )
            .filter(
                pl.col("changed_at").is_null()
                | (pl.col("changed_at") <= pl.col("start_date"))
            )
            .sort("changed_at", descending=True)
            .group_by(["issue_id", "sprint_id"])
            .first()
        )
    else:
        # No changelog - assume all current members were planned
        state_at_start = membership.with_columns(pl.lit(None).alias("action"))

    # Step 3: Join with issue creation dates
    state_with_created = state_at_start.join(
        issues_df.select(["id", "jira_created_at"]),
        left_on="issue_id",
        right_on="id",
        how="left",
    )

    # Step 4: Determine if planned
    # Planned if:
    # - Explicitly added before start (action='added')
    # - OR: No history AND created before start
    planned = state_with_created.with_columns(
        [
            (
                (pl.col("action") == "added")
                | (
                    pl.col("action").is_null()
                    & (pl.col("jira_created_at") <= pl.col("start_date"))
                )
            ).alias("is_planned")
        ]
    )

    return planned.select(["issue_id", "sprint_id", "is_planned"])


def extract_story_points(
    planned_df: pl.DataFrame,
    field_values_df: pl.DataFrame,
    field_keys_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Extract Story Points for planned issues.

    Fallback strategy:
    1. Try custom field "Story Points" (by name)
    2. Try customfield_10036, customfield_10016 (common Jira field IDs)
    3. Default to 0 if not found

    Args:
        planned_df: DataFrame with [issue_id, sprint_id, is_planned]
        field_values_df: Custom field values
        field_keys_df: Custom field definitions

    Returns:
        DataFrame with: [issue_id, sprint_id, story_points]

    Example:
        >>> sp_df = extract_story_points(planned, field_values, field_keys)
        >>> print(sp_df.select("story_points").describe())
    """
    if field_keys_df.is_empty():
        # No custom fields - return 0 story points
        return planned_df.select(["issue_id", "sprint_id"]).with_columns(
            pl.lit(0.0).alias("story_points")
        )

    # Step 1: Identify Story Points field ID(s)
    sp_fields = field_keys_df.filter(
        (
            pl.col("external_key").is_in(
                ["customfield_10036", "customfield_10016", "story_points"]
            )
        )
        | (pl.col("name").str.to_lowercase().str.contains("story point"))
    )

    if sp_fields.is_empty():
        # No Story Points field found
        return planned_df.select(["issue_id", "sprint_id"]).with_columns(
            pl.lit(0.0).alias("story_points")
        )

    # Step 2: Join planned issues with field values
    sp_values = (
        planned_df.join(field_values_df, on="issue_id", how="left")
        .join(sp_fields, left_on="field_key_id", right_on="id", how="inner")
        .with_columns(
            [
                # Try to parse as float, default to 0
                pl.when(pl.col("json_value").is_not_null())
                .then(pl.col("json_value").cast(pl.Float64, strict=False))
                .otherwise(0.0)
                .alias("story_points")
            ]
        )
        .select(["issue_id", "sprint_id", "story_points"])
        .group_by(["issue_id", "sprint_id"])
        .agg(pl.col("story_points").max())  # Take max if multiple fields/values
    )

    # Step 3: Left join back to planned issues (use 0 for missing values)
    result = planned_df.select(["issue_id", "sprint_id"]).join(
        sp_values, on=["issue_id", "sprint_id"], how="left"
    )

    return result.with_columns(pl.col("story_points").fill_null(0.0))


def identify_completed_issues(
    planned_df: pl.DataFrame,
    issues_df: pl.DataFrame,
    status_changelog_df: pl.DataFrame,
    done_status_ids: List[str],
    sprints_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Determine which planned issues were completed by sprint end.

    Business Rules:
    1. Issue resolved_at <= sprint.end_date → Completed
    2. Issue transitioned to Done status <= sprint.end_date → Completed
    3. Current status is Done AND sprint ended → Completed

    Args:
        planned_df: Planned issues [issue_id, sprint_id]
        issues_df: Issue details (status, resolved_at)
        status_changelog_df: Status change history
        done_status_ids: List of status IDs representing "Done"
        sprints_df: Sprint details (end_date)

    Returns:
        DataFrame with: [issue_id, sprint_id, is_completed]

    Example:
        >>> completed = identify_completed_issues(planned, issues, changelog, done_ids, sprints)
        >>> completion_rate = len(completed) / len(planned) * 100
    """
    # Join planned with sprint end dates
    with_end_dates = planned_df.join(
        sprints_df.select(["id", "end_date"]),
        left_on="sprint_id",
        right_on="id",
        how="left",
    )

    # Strategy 1: Resolved by end date
    resolved_by_end = (
        with_end_dates.join(
            issues_df.select(["id", "jira_resolved_at"]),
            left_on="issue_id",
            right_on="id",
            how="left",
        )
        .filter(
            pl.col("jira_resolved_at").is_not_null()
            & (pl.col("jira_resolved_at") <= pl.col("end_date"))
        )
        .select(["issue_id", "sprint_id"])
        .with_columns(pl.lit(True).alias("is_completed"))
    )

    # Strategy 2: Transitioned to Done by end date (from changelog)
    if not status_changelog_df.is_empty() and done_status_ids:
        done_by_changelog = (
            with_end_dates.join(status_changelog_df, on="issue_id", how="left")
            .filter(
                pl.col("to_status_id").is_in(done_status_ids)
                & (pl.col("changed_at") <= pl.col("end_date"))
            )
            .select(["issue_id", "sprint_id"])
            .unique()
            .with_columns(pl.lit(True).alias("is_completed"))
        )

        # Combine strategies (UNION)
        completed = pl.concat([resolved_by_end, done_by_changelog]).unique()
    else:
        completed = resolved_by_end

    # Strategy 3: Current status is Done (for sprints that already ended)
    if done_status_ids:
        done_by_current_status = (
            with_end_dates.join(
                issues_df.select(["id", "status_id"]),
                left_on="issue_id",
                right_on="id",
                how="left",
            )
            .filter(pl.col("status_id").is_in(done_status_ids))
            .select(["issue_id", "sprint_id"])
            .with_columns(pl.lit(True).alias("is_completed"))
        )

        completed = pl.concat([completed, done_by_current_status]).unique()

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
) -> pl.DataFrame:
    """
    Main orchestration function: Calculate Velocity facts.

    This function implements the complete Velocity calculation logic,
    replacing the complex SQL Materialized View with debuggable Python code.

    Args:
        sprints_df: Sprint definitions
        sprint_issues_df: Sprint-issue membership
        sprint_changelog_df: Sprint membership history
        issues_df: Issue details
        field_values_df: Custom field values
        field_keys_df: Custom field definitions
        status_changelog_df: Status change history
        boards_df: Board definitions
        board_columns_df: Board column configuration

    Returns:
        DataFrame ready to insert into metrics.fact_velocity

    Example:
        >>> velocity_df = calculate_velocity_facts(
        ...     sprints, sprint_issues, changelog, issues,
        ...     field_values, field_keys, status_changes, boards, columns
        ... )
        >>> print(velocity_df.columns)
        ['id', 'project_id', 'iteration_id', 'iteration_name', ...]
    """
    # Step 1: Identify Done statuses
    done_status_ids = get_done_status_ids(boards_df, board_columns_df)

    # Step 2: Identify planned issues
    planned = identify_planned_issues(
        sprint_issues_df, sprint_changelog_df, issues_df, sprints_df
    ).filter(
        pl.col("is_planned")
    )  # Keep only planned=True

    # Step 3: Extract story points for planned
    planned_with_sp = planned.join(
        extract_story_points(planned, field_values_df, field_keys_df),
        on=["issue_id", "sprint_id"],
        how="left",
    ).with_columns(pl.col("story_points").fill_null(0.0))

    # Step 4: Identify completed issues
    completed = identify_completed_issues(
        planned, issues_df, status_changelog_df, done_status_ids, sprints_df
    )

    # Step 5: Aggregate by sprint
    # First, aggregate planned metrics
    planned_agg = planned_with_sp.group_by("sprint_id").agg(
        [
            pl.count("issue_id").alias("planned_issues"),
            pl.sum("story_points").alias("planned_story_points"),
        ]
    )

    # Then, aggregate completed metrics (join planned with completed)
    completed_agg = (
        planned_with_sp.join(completed, on=["issue_id", "sprint_id"], how="inner")
        .group_by("sprint_id")
        .agg(
            [
                pl.count("issue_id").alias("completed_issues"),
                pl.sum("story_points").alias("completed_story_points"),
            ]
        )
    )

    # Step 6: Join with sprint details and combine aggregations
    velocity_agg = (
        sprints_df.join(planned_agg, left_on="id", right_on="sprint_id", how="left")
        .join(completed_agg, left_on="id", right_on="sprint_id", how="left")
        .with_columns(
            [
                # Fill nulls with 0 for sprints with no planned/completed issues
                pl.col("planned_issues").fill_null(0),
                pl.col("planned_story_points").fill_null(0.0),
                pl.col("completed_issues").fill_null(0),
                pl.col("completed_story_points").fill_null(0.0),
            ]
        )
        .select(
            [
                pl.col("project_id"),
                pl.col("id").alias("iteration_id"),
                pl.col("name").alias("iteration_name"),
                pl.col("start_date"),
                pl.col("end_date"),
                pl.col("planned_story_points"),
                pl.col("completed_story_points"),
                pl.col("planned_issues"),
                pl.col("completed_issues"),
            ]
        )
    )

    return velocity_agg


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
) -> pl.DataFrame:
    """
    Calculate Velocity sliced by Issue Type.

    This is the SAME logic as calculate_velocity_facts, but with
    an additional GROUP BY issue_type. This demonstrates DRY principle.

    Returns:
        DataFrame ready to insert into metrics.fact_velocity_slice
    """
    # Reuse existing logic
    done_status_ids = get_done_status_ids(boards_df, board_columns_df)

    planned = identify_planned_issues(
        sprint_issues_df, sprint_changelog_df, issues_df, sprints_df
    ).filter(pl.col("is_planned"))

    # Join with issue type
    planned_with_type = planned.join(
        issues_df.select(["id", "type_name"]),
        left_on="issue_id",
        right_on="id",
        how="left",
    )

    planned_with_sp = planned_with_type.join(
        extract_story_points(planned, field_values_df, field_keys_df),
        on=["issue_id", "sprint_id"],
        how="left",
    ).with_columns(pl.col("story_points").fill_null(0.0))

    completed = identify_completed_issues(
        planned, issues_df, status_changelog_df, done_status_ids, sprints_df
    )

    # Aggregate by sprint AND issue_type
    planned_agg = planned_with_sp.group_by(["sprint_id", "type_name"]).agg(
        [
            pl.count("issue_id").alias("planned_issues"),
            pl.sum("story_points").alias("planned_story_points"),
        ]
    )

    completed_agg = (
        planned_with_sp.join(completed, on=["issue_id", "sprint_id"], how="inner")
        .group_by(["sprint_id", "type_name"])
        .agg(
            [
                pl.count("issue_id").alias("completed_issues"),
                pl.sum("story_points").alias("completed_story_points"),
            ]
        )
    )

    # Join with sprint details
    velocity_slice = (
        planned_agg.join(completed_agg, on=["sprint_id", "type_name"], how="left")
        .join(
            sprints_df.select(["id", "project_id", "name", "start_date", "end_date"]),
            left_on="sprint_id",
            right_on="id",
            how="left",
        )
        .with_columns(
            [
                pl.col("completed_issues").fill_null(0),
                pl.col("completed_story_points").fill_null(0.0),
            ]
        )
        .select(
            [
                pl.col("project_id"),
                pl.col("sprint_id").alias("iteration_id"),
                pl.col("name").alias("iteration_name"),
                pl.col("start_date"),
                pl.col("end_date"),
                pl.col("type_name").alias("issue_type"),
                pl.col("planned_story_points"),
                pl.col("completed_story_points"),
                pl.col("planned_issues"),
                pl.col("completed_issues"),
            ]
        )
    )

    return velocity_slice
