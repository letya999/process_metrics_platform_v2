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
    Determine which issues were part of the sprint ("Planned/Committed") at the END of the sprint.

    User Definition:
    - "Planned" includes everything that was in the sprint at the moment it closed.
    - Includes "Scope Creep" (issues added mid-sprint).
    - Excludes issues that were removed from the sprint before it ended.

    Args:
        sprint_issues_df: Current sprint-issue membership (candidates)
        sprint_changelog_df: History of sprint membership changes
        issues_df: Issue details (unused in this logic, kept for interface compatibility)
        sprints_df: Sprint details (including end_date)

    Returns:
        DataFrame with columns: [issue_id, sprint_id, is_planned]
    """
    # Step 1: Get ALL candidates - from current membership AND changelog history
    # sprint_issues only contains issues currently in sprint (or at end)
    # But checking commitment requires seeing issues that were removed
    candidates = sprint_issues_df.select(["issue_id", "sprint_id"])

    if not sprint_changelog_df.is_empty():
        history_candidates = sprint_changelog_df.select(
            ["issue_id", "sprint_id"]
        ).unique()
        candidates = pl.concat([candidates, history_candidates]).unique()

    # Join with sprint timestamps
    membership = candidates.join(
        sprints_df.select(["id", "start_date", "end_date"]),
        left_on="sprint_id",
        right_on="id",
        how="inner",  # Only meaningful if we have sprint dates
    )

    # Step 2: Determine status AT START
    if (
        not sprint_changelog_df.is_empty()
        and "changed_at" in sprint_changelog_df.columns
    ):
        # Get last action at or before start_date
        actions_at_start = (
            sprint_changelog_df.join(
                sprints_df.select(["id", "start_date"]),
                left_on="sprint_id",
                right_on="id",
                how="inner",
            )
            .filter(
                pl.col("changed_at").is_null()
                | (pl.col("changed_at") <= pl.col("start_date"))
            )
            .sort("changed_at", descending=True)
            .unique(subset=["issue_id", "sprint_id"], keep="first")
            .select(
                ["issue_id", "sprint_id", pl.col("action").alias("action_at_start")]
            )
        )

        state = membership.join(
            actions_at_start, on=["issue_id", "sprint_id"], how="left"
        )
    else:
        # No changelog - fallback to viewing everything as added
        state = membership.with_columns(pl.lit("added").alias("action_at_start"))

    # Step 3: Filter - included if added before/at start OR snapshot (NULL)
    # IMPORTANT:
    # - If action_at_start is 'added' -> It was in sprint at start -> Planned
    # - If action_at_start is NULL:
    #   - If it is in sprint_issues (current membership) -> Likely snapshot -> Planned
    #   - If NOT in sprint_issues -> It was removed, but we have no add record?
    #     This is tricky. Assuming valid changelog, NULL means 'no event before start'.
    #     If the issue is in sprint_issues, it means it's there NOW. If no history, it was likely there at start (snapshot).
    #     If the issue is NOT in sprint_issues (removed) and has NULL start action, it clearly wasn't there at start.

    # Let's verify membership in sprint_issues for the snapshot case
    current_members = sprint_issues_df.with_columns(pl.lit(True).alias("is_current"))

    state_with_curr = state.join(
        current_members.select(["issue_id", "sprint_id", "is_current"]),
        on=["issue_id", "sprint_id"],
        how="left",
    )

    planned = state_with_curr.with_columns(
        (
            (pl.col("action_at_start") == "added")
            | (pl.col("action_at_start").is_null() & pl.col("is_current").is_not_null())
        )
        .fill_null(False)
        .alias("is_planned")
    )

    return planned.select(["issue_id", "sprint_id", "is_planned"])


def extract_story_points(
    planned_df: pl.DataFrame,
    field_values_df: pl.DataFrame,
    field_keys_df: pl.DataFrame,
    field_value_changelog_df: pl.DataFrame,
    sprints_df: pl.DataFrame,
    sprint_changelog_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Extract Story Points at COMMITMENT time (Sprint Start).

    Takes the SP estimate valid at the moment the sprint started.
    - If issue was in sprint at start: use SP at start_date
    - Changes during sprint are NOT included in "Planned" SP (Commitment).

    Args:
        planned_df: DataFrame with [issue_id, sprint_id, is_planned]
        field_values_df: Custom field values (current state, fallback)
        field_keys_df: Custom field definitions
        field_value_changelog_df: Field value history
        sprints_df: Sprint details (need start_date)
        sprint_changelog_df: Not used but kept for interface compatibility

    Returns:
        DataFrame with: [issue_id, sprint_id, story_points]
    """
    if field_keys_df.is_empty():
        return planned_df.select(["issue_id", "sprint_id"]).with_columns(
            pl.lit(0.0).alias("story_points")
        )

    # Step 1: Identify Story Points field ID(s)
    sp_fields = field_keys_df.filter(
        (pl.col("external_key").is_in(["customfield_10036", "story_points"]))
        | (pl.col("name").str.to_lowercase().str.contains("story point"))
    )

    if sp_fields.is_empty():
        return planned_df.select(["issue_id", "sprint_id"]).with_columns(
            pl.lit(0.0).alias("story_points")
        )

    # Step 2: Join with start_date to get commitment timestamp
    planned_with_dates = planned_df.join(
        sprints_df.select(["id", "start_date"]),
        left_on="sprint_id",
        right_on="id",
        how="left",
    )

    # Step 3: Get SP value as of start_date
    sp_field_ids = sp_fields.select("id").to_series().to_list()

    if not field_value_changelog_df.is_empty() and sp_field_ids:
        # Filter changelog for SP fields only
        sp_changelog = field_value_changelog_df.filter(
            pl.col("field_key_id").is_in(sp_field_ids)
        )

        # Find last SP change BEFORE or AT start_date
        historical_sp = (
            planned_with_dates.join(sp_changelog, on="issue_id", how="left")
            .filter(
                pl.col("changed_at").is_null()
                | (pl.col("changed_at") <= pl.col("start_date"))
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
                    .alias("story_points")
                ]
            )
            .select(["issue_id", "sprint_id", "story_points"])
        )
    else:
        historical_sp = pl.DataFrame()

    # Fallback to current values if no changelog
    if historical_sp.is_empty():
        current_sp = (
            planned_df.join(field_values_df, on="issue_id", how="left")
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
                    .alias("story_points")
                ]
            )
            .select(["issue_id", "sprint_id", "story_points"])
            .group_by(["issue_id", "sprint_id"])
            .agg(pl.col("story_points").max())
        )
        sp_values = current_sp
    else:
        sp_values = historical_sp

    # Step 4: Left join back to planned issues (use 0 for missing values)
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
    1. Issue resolved_at is within [sprint.start_date, sprint.effective_end_date]
       where effective_end_date is the actual completion date (if clicked) or scheduled end date.
    2. Start Date Constraint: Issues resolved BEFORE sprint start are NOT counted (Velocity = work DONE in sprint).
    3. End Date Constraint: Issues resolved AFTER sprint closed (with grace period) are NOT counted.

    Args:
        planned_df: Planned issues [issue_id, sprint_id]
        issues_df: Issue details (status, resolved_at)
        status_changelog_df: Status change history
        done_status_ids: List of status IDs representing "Done"
        sprints_df: Sprint details (start_date, end_date, complete_date)

    Returns:
        DataFrame with: [issue_id, sprint_id, is_completed]
    """
    # Join planned with sprint dates
    # We need start_date, end_date, and complete_date
    sprint_dates = sprints_df.select(["id", "start_date", "end_date", "complete_date"])

    with_dates = planned_df.join(
        sprint_dates,
        left_on="sprint_id",
        right_on="id",
        how="left",
    ).with_columns(
        [
            # Effective end date: Use complete_date if available (button clicked), else end_date
            pl.coalesce(["complete_date", "end_date"]).alias("effective_end_date")
        ]
    )

    # Strategy 1: Resolved within the sprint window AND status is Done
    # Condition: start_date <= resolved_at <= effective_end_date AND status_id IN done_status_ids
    resolved_in_sprint = (
        with_dates.join(
            issues_df.select(["id", "jira_resolved_at", "status_id"]),
            left_on="issue_id",
            right_on="id",
            how="left",
        )
        .filter(
            pl.col("jira_resolved_at").is_not_null()
            & (pl.col("jira_resolved_at") >= pl.col("start_date"))
            & (pl.col("jira_resolved_at") <= pl.col("effective_end_date"))
            & (pl.col("status_id").is_in(done_status_ids))
        )
        .select(["issue_id", "sprint_id"])
        .with_columns(pl.lit(True).alias("is_completed"))
    )

    # Strategy 2: Transitioned to Done within the sprint window (from changelog)
    # Useful if jira_resolved_at is missing but status changed
    if not status_changelog_df.is_empty() and done_status_ids:
        done_by_changelog = (
            with_dates.join(status_changelog_df, on="issue_id", how="left")
            .filter(
                pl.col("to_status_id").is_in(done_status_ids)
                & (pl.col("changed_at") >= pl.col("start_date"))
                & (pl.col("changed_at") <= pl.col("effective_end_date"))
            )
            .select(["issue_id", "sprint_id"])
            .unique()
            .with_columns(pl.lit(True).alias("is_completed"))
        )

        # Combine strategies (UNION)
        completed = pl.concat([resolved_in_sprint, done_by_changelog]).unique()
    else:
        completed = resolved_in_sprint

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

    # Step 3: Extract story points for planned (HISTORICAL values at commitment time)
    planned_with_sp = planned.join(
        extract_story_points(
            planned_df=planned,
            field_values_df=field_values_df,
            field_keys_df=field_keys_df,
            field_value_changelog_df=field_value_changelog_df,
            sprints_df=sprints_df,
            sprint_changelog_df=sprint_changelog_df,
        ),
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
    field_value_changelog_df: pl.DataFrame,
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
        extract_story_points(
            planned_df=planned,
            field_values_df=field_values_df,
            field_keys_df=field_keys_df,
            field_value_changelog_df=field_value_changelog_df,
            sprints_df=sprints_df,
            sprint_changelog_df=sprint_changelog_df,
        ),
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
