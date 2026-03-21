import logging

import polars as pl
from dagster import AssetCheckResult, AssetExecutionContext, asset, asset_check

from pipelines.calculations import sprint_health as sprint_health_logic
from pipelines.calculations.commitment_resolver import (
    identify_commitment_points_from_rule,
    load_commitment_rules_for_calc,
    resolve_rule_from_cache,
)
from pipelines.resources.database import DatabaseResource
from pipelines.utils.metric_registry import get_calculation_id, get_project_agg_id
from pipelines.utils.polars_db import read_table, write_fact_values

logger = logging.getLogger(__name__)


@asset(
    group_name="metrics",
    deps=[
        "clean_jira_sprints",
        "clean_jira_sprint_issues",
        "clean_jira_sprint_issues_changelog",
        "clean_jira_issues",
        "clean_jira_field_values",
        "clean_jira_field_keys",
        "clean_jira_issue_status_changelog",
        "clean_jira_board_columns",
        "clean_jira_boards",
    ],
    description="Calculate Sprint Health metrics",
    compute_kind="python",
)
def calculate_sprint_health(
    context: AssetExecutionContext,
    database: DatabaseResource,
):
    engine = database.get_engine()

    # 1. Load Data
    sprints_df = read_table(
        engine,
        "SELECT * FROM clean_jira.sprints WHERE state IN ('closed', 'active') AND start_date IS NOT NULL",
    )
    if sprints_df.is_empty():
        return {"status": "skipped", "reason": "No sprints found"}

    sprint_issues_df = read_table(engine, "SELECT * FROM clean_jira.sprint_issues")
    sprint_changelog_df = read_table(
        engine, "SELECT * FROM clean_jira.sprint_issues_changelog"
    )
    issues_df = read_table(
        engine,
        """
        SELECT i.id, i.project_id, i.issue_key, i.created_at, i.updated_at, i.type_id as issue_type_id, it.name as type_name
        FROM clean_jira.issues i
        LEFT JOIN clean_jira.issue_types it ON i.type_id = it.id
    """,
    )
    field_keys_df = read_table(engine, "SELECT * FROM clean_jira.field_keys")
    field_values_df = read_table(
        engine,
        "SELECT issue_id, field_key_id, json_value::text as json_value FROM clean_jira.field_values",
    )
    field_value_changelog_df = read_table(
        engine,
        """
        SELECT issue_id, field_key_id, old_value::text as old_value, new_value::text as new_value, changed_at as change_time
        FROM clean_jira.field_value_changelog
    """,
    )
    issue_status_changelog_df = read_table(
        engine, "SELECT * FROM clean_jira.issue_status_changelog"
    )
    board_columns_df = read_table(
        engine,
        """
        SELECT bc.id, bc.board_id, bc.name, bcs.status_id, bc.position
        FROM clean_jira.board_columns bc
        LEFT JOIN clean_jira.board_column_statuses bcs ON bcs.board_column_id = bc.id
    """,
    )
    boards_df = read_table(engine, "SELECT * FROM clean_jira.boards")

    # 2. Resolve IDs and Rules
    project_ids = sprints_df["project_id"].unique().to_list()
    project_agg_map = {pid: get_project_agg_id(engine, pid) for pid in project_ids}

    # SP field key (heuristic from velocity)
    sp_fields = field_keys_df.filter(
        (
            pl.col("external_key").is_in(
                ["customfield_10036", "customfield_10016", "story_points"]
            )
        )
        | (pl.col("name").str.to_lowercase().str.contains("story point"))
    )
    sp_field_key_id = sp_fields["id"][0] if not sp_fields.is_empty() else None

    # Done status IDs (from commitment rules)
    lead_time_rules = load_commitment_rules_for_calc(engine, "lead_time_days")

    # 3. Calculations
    all_facts = []

    # A. Scope Changes
    scope_changes = sprint_health_logic.calculate_sprint_scope_changes(
        sprints_df,
        sprint_changelog_df,
        issues_df,
        field_values_df,
        field_keys_df,
        field_value_changelog_df,
    )

    calc_map_scope = {
        "added_count": get_calculation_id(engine, "sprint_added_issues_count"),
        "added_sp": get_calculation_id(engine, "sprint_added_sp_sum"),
        "removed_count": get_calculation_id(engine, "sprint_removed_issues_count"),
        "removed_sp": get_calculation_id(engine, "sprint_removed_sp_sum"),
    }

    for col, calc_id in calc_map_scope.items():
        facts = scope_changes.select(
            [
                pl.lit(calc_id).alias("metric_id"),
                pl.col("project_id").replace(project_agg_map).alias("project_agg_id"),
                pl.col("start_date")
                .dt.strftime("%Y%m%d")
                .cast(pl.Int32)
                .alias("time_id"),
                pl.col(col).alias("value"),
                pl.lit("sprint").alias("entity_type"),
                pl.col("iteration_id").alias("entity_id"),
            ]
        )
        all_facts.append(facts)

    # B. Spillover
    spillover = sprint_health_logic.calculate_sprint_spillover(
        sprints_df, sprint_issues_df
    )
    calc_id_spillover = get_calculation_id(engine, "sprint_spillover_count")
    facts_spillover = spillover.select(
        [
            pl.lit(calc_id_spillover).alias("metric_id"),
            pl.col("project_id").replace(project_agg_map).alias("project_agg_id"),
            pl.col("start_date").dt.strftime("%Y%m%d").cast(pl.Int32).alias("time_id"),
            pl.col("spillover_count").alias("value"),
            pl.lit("sprint").alias("entity_type"),
            pl.col("iteration_id").alias("entity_id"),
        ]
    )
    all_facts.append(facts_spillover)

    # C. Burndown and Activation Velocity (Daily)
    # We need to resolve done_status_ids and initial_status_id per project/board
    calc_id_burndown = get_calculation_id(engine, "sprint_burndown_remaining_sp")
    calc_id_activation = get_calculation_id(engine, "activation_velocity_pct")

    # Activation rule calc_code is usually 'lead_time_days' or specific 'activation_velocity_pct'
    activation_rules = load_commitment_rules_for_calc(engine, "activation_velocity_pct")
    if activation_rules.is_empty():
        activation_rules = lead_time_rules

    # We iterate over sprints to handle different board configs
    for sprint in sprints_df.to_dicts():
        p_id = sprint["project_id"]
        b_id = boards_df.filter(pl.col("project_id") == p_id).select("id").to_series()
        b_id = b_id[0] if not b_id.is_empty() else None

        if not b_id:
            continue

        board_cols = board_columns_df.filter(pl.col("board_id") == b_id)
        rule = resolve_rule_from_cache(lead_time_rules, p_id, b_id)
        if not rule:
            continue

        points = identify_commitment_points_from_rule(rule, board_cols)
        done_ids = points.get("end_status_ids", [])

        # Burndown
        burndown = sprint_health_logic.calculate_sprint_burndown(
            pl.DataFrame([sprint]),
            sprint_issues_df,
            sprint_changelog_df,
            issue_status_changelog_df,
            done_ids,
            issues_df,
            field_values_df,
            field_keys_df,
            field_value_changelog_df,
        )
        if not burndown.is_empty():
            facts_burndown = burndown.select(
                [
                    pl.lit(calc_id_burndown).alias("metric_id"),
                    pl.col("project_id")
                    .replace(project_agg_map)
                    .alias("project_agg_id"),
                    pl.col("time_date")
                    .dt.strftime("%Y%m%d")
                    .cast(pl.Int32)
                    .alias("time_id"),
                    pl.col("remaining_sp").alias("value"),
                    pl.lit("sprint").alias("entity_type"),
                    pl.col("iteration_id").alias("entity_id"),
                ]
            )
            all_facts.append(facts_burndown)

        # Activation
        act_rule = resolve_rule_from_cache(activation_rules, p_id, b_id)
        if act_rule:
            act_points = identify_commitment_points_from_rule(act_rule, board_cols)
            # Initial status is the start of commitment
            initial_status_ids = act_points.get("start_status_ids", [])
            if initial_status_ids:
                activation = sprint_health_logic.calculate_activation_velocity(
                    pl.DataFrame([sprint]),
                    sprint_issues_df,
                    sprint_changelog_df,
                    issue_status_changelog_df,
                    issues_df,
                    field_values_df,
                    field_keys_df,
                    field_value_changelog_df,
                    initial_status_ids[0],
                )
                if not activation.is_empty():
                    facts_activation = activation.select(
                        [
                            pl.lit(calc_id_activation).alias("metric_id"),
                            pl.col("project_id")
                            .replace(project_agg_map)
                            .alias("project_agg_id"),
                            pl.col("time_date")
                            .dt.strftime("%Y%m%d")
                            .cast(pl.Int32)
                            .alias("time_id"),
                            pl.col("activation_pct").alias("value"),
                            pl.lit("sprint").alias("entity_type"),
                            pl.col("iteration_id").alias("entity_id"),
                        ]
                    )
                    all_facts.append(facts_activation)

    # D. Unestimated Closed
    # Use lead_time_rules for done status
    calc_id_unestimated = get_calculation_id(engine, "unestimated_closed_count")
    if sp_field_key_id:
        for sprint in sprints_df.to_dicts():
            p_id = sprint["project_id"]
            b_id = (
                boards_df.filter(pl.col("project_id") == p_id).select("id").to_series()
            )
            b_id = b_id[0] if not b_id.is_empty() else None
            if not b_id:
                continue

            rule = resolve_rule_from_cache(lead_time_rules, p_id, b_id)
            if not rule:
                continue
            points = identify_commitment_points_from_rule(
                rule, board_columns_df.filter(pl.col("board_id") == b_id)
            )
            done_ids = points.get("end_status_ids", [])

            unestimated = sprint_health_logic.calculate_unestimated_closed(
                pl.DataFrame([sprint]),
                sprint_issues_df,
                sprint_changelog_df,
                issues_df,
                issue_status_changelog_df,
                done_ids,
                field_values_df,
                sp_field_key_id,
            )
            if not unestimated.is_empty():
                facts_unestimated = unestimated.select(
                    [
                        pl.lit(calc_id_unestimated).alias("metric_id"),
                        pl.col("project_id")
                        .replace(project_agg_map)
                        .alias("project_agg_id"),
                        pl.col("start_date")
                        .dt.strftime("%Y%m%d")
                        .cast(pl.Int32)
                        .alias("time_id"),
                        pl.col("unestimated_count").alias("value"),
                        pl.lit("sprint").alias("entity_type"),
                        pl.col("iteration_id").alias("entity_id"),
                    ]
                )
                all_facts.append(facts_unestimated)

    # E. Field Value Sprint Pct (Parameterized)
    calc_id_field_pct = get_calculation_id(engine, "field_value_sprint_pct")
    # Load settings
    settings_df = read_table(
        engine,
        """
        SELECT cs.* FROM metrics.calculation_settings cs
        WHERE cs.target_calculation_id = :calc_id AND cs.enabled = true
    """,
        params={"calc_id": calc_id_field_pct},
    )

    if not settings_df.is_empty():
        for setting in settings_df.to_dicts():
            s_json = setting["settings_json"]
            f_name = s_json.get("field_name")
            f_val = s_json.get("field_value")
            target_p_id = setting["project_id"]

            if not f_name or not f_val:
                continue

            # Filter sprints for this project or all if target_p_id is None
            sprints_subset = sprints_df
            if target_p_id:
                sprints_subset = sprints_df.filter(pl.col("project_id") == target_p_id)

            if sprints_subset.is_empty():
                continue

            field_pct = sprint_health_logic.calculate_field_value_sprint_pct(
                sprints_subset,
                sprint_issues_df,
                issues_df,
                f_name,
                f_val,
                field_values_df,
                field_keys_df,
            )

            if not field_pct.is_empty():
                facts_field_pct = field_pct.select(
                    [
                        pl.lit(calc_id_field_pct).alias("metric_id"),
                        pl.col("project_id")
                        .replace(project_agg_map)
                        .alias("project_agg_id"),
                        pl.col("start_date")
                        .dt.strftime("%Y%m%d")
                        .cast(pl.Int32)
                        .alias("time_id"),
                        pl.col("field_pct").alias("value"),
                        pl.lit("sprint").alias("entity_type"),
                        pl.col("iteration_id").alias("entity_id"),
                        pl.lit(setting["id"]).alias("settings_id"),
                    ]
                )
                all_facts.append(facts_field_pct)

    # 4. Write to DB
    if not all_facts:
        return {"status": "no_data"}

    final_df = pl.concat(
        [f for f in all_facts if not f.is_empty()], how="diagonal_relaxed"
    )

    metric_ids = final_df["metric_id"].unique().to_list()
    project_agg_ids = final_df["project_agg_id"].unique().to_list()
    time_id_start = final_df["time_id"].min()
    time_id_end = final_df["time_id"].max()

    rows_written = write_fact_values(
        final_df,
        engine,
        metric_ids=metric_ids,
        project_agg_ids=project_agg_ids,
        time_id_start=time_id_start,
        time_id_end=time_id_end,
    )

    return {
        "status": "success",
        "rows_written": rows_written,
        "metrics_calculated": len(metric_ids),
    }


@asset_check(asset=calculate_sprint_health)
def sprint_health_data_quality_check(database: DatabaseResource):
    # Basic check for non-negative values
    engine = database.get_engine()
    calc_codes = [
        "sprint_added_issues_count",
        "sprint_added_sp_sum",
        "sprint_removed_issues_count",
        "sprint_removed_sp_sum",
        "sprint_spillover_count",
        "sprint_burndown_remaining_sp",
    ]

    for code in calc_codes:
        calc_id = get_calculation_id(engine, code)
        df = read_table(
            engine,
            "SELECT COUNT(*) as cnt FROM metrics.fact_values WHERE metric_id = :calc_id AND value < 0",
            params={"calc_id": calc_id},
        )
        if not df.is_empty() and df[0, "cnt"] > 0:
            return AssetCheckResult(
                passed=False, metadata={"error": f"Negative values found for {code}"}
            )

    return AssetCheckResult(passed=True)
