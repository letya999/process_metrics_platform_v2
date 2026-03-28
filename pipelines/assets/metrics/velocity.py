"""
Velocity Metrics Dagster Asset (Generic Long Metric Store)
"""

import logging
from typing import Any

import polars as pl
from dagster import AssetCheckResult, AssetExecutionContext, asset, asset_check

from pipelines.calculations import velocity as velocity_logic
from pipelines.calculations.commitment_resolver import (
    identify_commitment_points_from_rule,
    load_commitment_rules_for_calc,
    resolve_commitment_columns,
    resolve_rule_from_cache,
)
from pipelines.calculations.slicing_utils import apply_slicing, get_slice_rules
from pipelines.resources.database import DatabaseResource
from pipelines.utils.metric_registry import (
    get_calculation_id,
    get_definition_id,
    get_project_agg_id,
    resolve_unit_field,
)
from pipelines.utils.polars_db import read_table, write_fact_values

logger = logging.getLogger(__name__)


def _resolve_done_status_ids_from_commitment_rules(
    engine,
    boards_df: pl.DataFrame,
    board_columns_df: pl.DataFrame,
) -> list[str]:
    """
    Resolve done statuses from commitment rules table.

    Priority:
    1. Rule for velocity_completed_sp.
    2. Rule for lead_time_days (shared commitment points convention).
    """
    if boards_df.is_empty() or board_columns_df.is_empty():
        return []

    velocity_rules = load_commitment_rules_for_calc(engine, "velocity_completed_sp")
    lead_time_rules = load_commitment_rules_for_calc(engine, "lead_time_days")
    done_status_ids: list[str] = []

    for board in boards_df.to_dicts():
        b_id = board["id"]
        p_id = board["project_id"]
        board_cols = board_columns_df.filter(pl.col("board_id") == b_id)
        if board_cols.is_empty():
            continue

        rule = resolve_rule_from_cache(
            velocity_rules, p_id, b_id
        ) or resolve_rule_from_cache(lead_time_rules, p_id, b_id)

        if not rule:
            # DB fallback in case cache is empty/stale.
            try:
                rule = resolve_commitment_columns(
                    engine, p_id, b_id, "velocity_completed_sp"
                )
            except Exception as exc:
                logger.warning(
                    "Failed resolve_commitment_columns for velocity_completed_sp (project_id=%s, board_id=%s): %s",
                    p_id,
                    b_id,
                    exc,
                )
                rule = None
            if not rule:
                try:
                    rule = resolve_commitment_columns(
                        engine, p_id, b_id, "lead_time_days"
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed resolve_commitment_columns for lead_time_days (project_id=%s, board_id=%s): %s",
                        p_id,
                        b_id,
                        exc,
                    )
                    rule = None

        if rule:
            points = identify_commitment_points_from_rule(rule, board_cols)
            done_status_ids.extend(points.get("end_status_ids", []))

    return sorted(
        {
            str(status_id).lower()
            for status_id in done_status_ids
            if status_id is not None
        }
    )


@asset(
    group_name="metrics",
    deps=[
        "clean_jira_issues",
        "clean_jira_issue_types",
        "clean_jira_sprints",
        "clean_jira_boards",
        "clean_jira_board_columns",
        "clean_jira_sprint_issues",
        "clean_jira_sprint_issues_changelog",
        "clean_jira_issue_status_changelog",
        "clean_jira_field_values",
        "clean_jira_field_keys",
    ],
    description="Calculate Velocity facts and write to generic fact_values",
    metadata={
        "grain": "mixed",
        "unit": "mixed",
        "calculation_logic": "See asset implementation and referenced calculation modules.",
    },
    compute_kind="python",
)
def calculate_velocity(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    engine = database.get_engine()

    # 1. Resolve metadata
    def_id = get_definition_id(engine, "velocity")
    calc_map = {
        "planned_story_points": get_calculation_id(engine, "velocity_planned_sp"),
        "completed_story_points": get_calculation_id(engine, "velocity_completed_sp"),
        "planned_issues": get_calculation_id(engine, "velocity_planned_count"),
        "completed_issues": get_calculation_id(engine, "velocity_completed_count"),
    }
    metric_ids = list(calc_map.values())

    context.log.info("Loading data from clean_jira schema...")

    # Load data
    sprints_df = read_table(
        engine,
        """
        SELECT DISTINCT s.id, s.project_id, s.name, s.start_date, s.end_date, s.complete_date, p.external_key AS project_key
        FROM clean_jira.sprints s
        JOIN clean_jira.projects p ON s.project_id = p.id
        INNER JOIN clean_jira.sprint_issues si ON si.sprint_id = s.id
        INNER JOIN clean_jira.issues i ON i.id = si.issue_id
        INNER JOIN clean_jira.issue_types it ON it.id = i.type_id
        WHERE s.start_date IS NOT NULL
          AND s.complete_date IS NOT NULL
          AND it.name NOT ILIKE '%%sub%%'
        """,
    )

    if sprints_df.is_empty():
        return {"status": "skipped", "reason": "No sprints found"}

    # Map project_agg_ids dynamically
    project_ids = sprints_df["project_id"].unique().to_list()
    project_agg_map = {pid: get_project_agg_id(engine, pid) for pid in project_ids}

    sprint_issues_df = read_table(
        engine,
        """
        SELECT DISTINCT si.issue_id, si.sprint_id
        FROM clean_jira.sprint_issues si
        JOIN clean_jira.issues i ON i.id = si.issue_id
        JOIN clean_jira.issue_types it ON it.id = i.type_id
        WHERE it.name NOT ILIKE '%%sub%%'
        """,
    )

    # Exclude changelog events recorded AFTER a sprint was closed (complete_date).
    # Retroactive membership additions (e.g. issues added months after sprint closed)
    # corrupt commitment and final-scope calculations.
    sprint_changelog_df = read_table(
        engine,
        """
        SELECT sic.issue_id, sic.sprint_id, sic.action, sic.changed_at
        FROM clean_jira.sprint_issues_changelog sic
        JOIN clean_jira.sprints s ON s.id = sic.sprint_id
        WHERE s.complete_date IS NULL OR sic.changed_at <= s.complete_date
        """,
    )

    issues_df = read_table(
        engine,
        """
        SELECT i.id, i.project_id, i.external_key AS key, it.name AS type_name,
               i.status_id,
            i.jira_created_at,
               i.jira_resolved_at
        FROM clean_jira.issues i
        LEFT JOIN clean_jira.issue_types it ON i.type_id = it.id
        """,
    )

    field_keys_df = read_table(
        engine, "SELECT id, external_key, name FROM clean_jira.field_keys"
    )

    field_values_df = read_table(
        engine,
        "SELECT issue_id, field_key_id, json_value::text AS json_value FROM clean_jira.field_values",
    )

    status_changelog_df = read_table(
        engine,
        "SELECT issue_id, from_status_id, to_status_id, changed_at FROM clean_jira.issue_status_changelog",
    )

    boards_df = read_table(engine, "SELECT id, project_id, name FROM clean_jira.boards")

    board_columns_df = read_table(
        engine,
        """
        SELECT bc.id, bc.board_id, bc.name, bcs.status_id, bc.position
        FROM clean_jira.board_columns bc
        LEFT JOIN clean_jira.board_column_statuses bcs ON bcs.board_column_id = bc.id
        """,
    )

    field_value_changelog_df = read_table(
        engine,
        """
        SELECT issue_id, field_key_id,
               old_value::text as old_value,
               new_value::text as new_value,
               changed_at
        FROM clean_jira.field_value_changelog
        """,
    )

    issue_statuses_df = read_table(
        engine, "SELECT id, name, category FROM clean_jira.issue_statuses"
    )
    done_status_ids = _resolve_done_status_ids_from_commitment_rules(
        engine, boards_df, board_columns_df
    )

    # Resolve story_points field keys via metrics.units, per project.
    # Falls back to heuristic inside calculate_velocity_facts if no binding found.
    sp_field_key_override: list[str] = []
    for p_id in project_ids:
        unit_info = resolve_unit_field(engine, p_id, "story_points")
        if unit_info and unit_info.get("source_field_id"):
            fk_id = str(unit_info["source_field_id"])
            if fk_id not in sp_field_key_override:
                sp_field_key_override.append(fk_id)

    context.log.info(
        "story_points field key override from metrics.units: %s",
        sp_field_key_override or "none (using heuristic)",
    )

    # 2. Calculate BASE velocity facts
    velocity_wide = velocity_logic.calculate_velocity_facts(
        sprints_df=sprints_df,
        sprint_issues_df=sprint_issues_df,
        sprint_changelog_df=sprint_changelog_df,
        issues_df=issues_df,
        field_values_df=field_values_df,
        field_keys_df=field_keys_df,
        status_changelog_df=status_changelog_df,
        boards_df=boards_df,
        board_columns_df=board_columns_df,
        field_value_changelog_df=field_value_changelog_df,
        issue_statuses_df=issue_statuses_df,
        done_status_ids=done_status_ids or None,
        allow_current_status_fallback=False,
        sp_field_key_ids_override=sp_field_key_override or None,
    )

    if velocity_wide.is_empty():
        return {"status": "no_data"}

    # 3. Transform to Long Format (fact_values)
    def transform_to_fact_values(df_wide, slice_rule_id=None, slice_value=None):
        if df_wide.is_empty():
            return pl.DataFrame()

        value_vars = [
            "planned_story_points",
            "completed_story_points",
            "planned_issues",
            "completed_issues",
        ]

        melted = df_wide.melt(
            id_vars=["project_id", "iteration_id", "end_date"],
            value_vars=value_vars,
            variable_name="calc_code",
            value_name="value",
        )

        # Map IDs and add static columns
        mapped = melted.with_columns(
            [
                pl.col("calc_code").replace(calc_map).alias("metric_id"),
                pl.col("project_id").replace(project_agg_map).alias("project_agg_id"),
                # end_date -> time_id (YYYYMMDD)
                pl.col("end_date")
                .dt.strftime("%Y%m%d")
                .cast(pl.Int32)
                .alias("time_id"),
                pl.lit("sprint").alias("entity_type"),
                pl.col("iteration_id").cast(pl.Utf8).alias("entity_id"),
                pl.lit(slice_rule_id)
                .cast(pl.Utf8)
                .alias("slice_rule_id"),  # Ensure Utf8
                pl.lit(None).alias("commitment_rule_id"),
                pl.lit(None).cast(pl.Datetime("us", "UTC")).alias("event_start_at"),
                pl.lit(None).cast(pl.Datetime("us", "UTC")).alias("event_end_at"),
            ]
        )

        if slice_value is not None:
            mapped = mapped.with_columns(
                pl.lit(str(slice_value)).cast(pl.Utf8).alias("slice_value")
            )
        else:
            mapped = mapped.with_columns(
                pl.lit(None).cast(pl.Utf8).alias("slice_value")
            )

        return mapped.select(
            [
                "metric_id",
                "project_agg_id",
                "time_id",
                "value",
                "entity_type",
                "entity_id",
                "slice_rule_id",
                "slice_value",
                "commitment_rule_id",
                "event_start_at",
                "event_end_at",
            ]
        ).drop_nulls(subset=["value"])

    base_facts = transform_to_fact_values(velocity_wide)

    # 4. Calculate Sliced facts
    rules_df = get_slice_rules(engine, target_definition_id=def_id)
    issues_for_slicing = issues_df.with_columns(pl.col("type_name").alias("issue_type"))

    def velocity_slice_calc(df_subset):
        # Scope sprint-related data to only the project(s) in this subset.
        # Without this, every slice call processes ALL projects' sprints and
        # discards empty rows afterwards — O(N_projects * N_types) fan-out.
        subset_pids = (
            df_subset.select("project_id").drop_nulls().unique().to_series().to_list()
        )
        sub_sprints = sprints_df.filter(pl.col("project_id").is_in(subset_pids))
        if sub_sprints.is_empty():
            return pl.DataFrame()
        sub_sprint_ids = sub_sprints.select("id").to_series().to_list()
        sub_boards = boards_df.filter(pl.col("project_id").is_in(subset_pids))
        sub_board_ids = sub_boards.select("id").to_series().to_list()

        return velocity_logic.calculate_velocity_facts(
            sprints_df=sub_sprints,
            sprint_issues_df=sprint_issues_df.filter(
                pl.col("sprint_id").is_in(sub_sprint_ids)
            ),
            sprint_changelog_df=sprint_changelog_df.filter(
                pl.col("sprint_id").is_in(sub_sprint_ids)
            ),
            issues_df=df_subset,
            field_values_df=field_values_df,
            field_keys_df=field_keys_df,
            status_changelog_df=status_changelog_df,
            boards_df=sub_boards,
            board_columns_df=board_columns_df.filter(
                pl.col("board_id").is_in(sub_board_ids)
            ),
            field_value_changelog_df=field_value_changelog_df,
            issue_statuses_df=issue_statuses_df,
            done_status_ids=done_status_ids or None,
            allow_current_status_fallback=False,
            sp_field_key_ids_override=sp_field_key_override or None,
        )

    all_facts = [base_facts]

    if not rules_df.is_empty():
        for rule in rules_df.to_dicts():
            rule_id = rule["slice_rule_id"]
            sliced_wide = apply_slicing(
                issues_for_slicing,
                rules_df.filter(pl.col("slice_rule_id") == rule_id),
                velocity_slice_calc,
                engine=engine,
                source_table="clean_jira.issues",
            )

            if sliced_wide.is_empty():
                continue

            # If apply_slicing implementation already provides slice_value, preserve it.
            if "slice_value" in sliced_wide.columns:
                groups = sliced_wide.partition_by(["slice_value"])
                for group_df in groups:
                    slice_val = group_df["slice_value"][0]
                    filtered_group = group_df.filter(
                        (pl.col("planned_issues") > 0)
                        | (pl.col("completed_issues") > 0)
                    )
                    if not filtered_group.is_empty():
                        facts = transform_to_fact_values(
                            filtered_group,
                            slice_rule_id=rule_id,
                            slice_value=slice_val,
                        )
                        all_facts.append(facts)
            else:
                filtered_group = sliced_wide.filter(
                    (pl.col("planned_issues") > 0) | (pl.col("completed_issues") > 0)
                )
                if not filtered_group.is_empty():
                    facts = transform_to_fact_values(
                        filtered_group,
                        slice_rule_id=rule_id,
                        slice_value=None,
                    )
                    all_facts.append(facts)

    final_df = pl.concat(all_facts)

    # 5. Write to DB
    time_id_start = final_df["time_id"].min()
    time_id_end = final_df["time_id"].max()
    project_agg_ids = list(project_agg_map.values())

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
        "sprints_processed": len(velocity_wide),
        "metric_ids": metric_ids,
    }


@asset_check(asset=calculate_velocity)
def velocity_data_quality_check(database: DatabaseResource) -> AssetCheckResult:
    engine = database.get_engine()
    calc_codes = [
        "velocity_planned_sp",
        "velocity_completed_sp",
        "velocity_planned_count",
        "velocity_completed_count",
    ]
    metric_counts: dict[str, int] = {}
    negative_counts: dict[str, int] = {}

    for calc_code in calc_codes:
        calc_id = get_calculation_id(engine, calc_code)
        query = """
        SELECT
            COUNT(*) AS row_count,
            SUM(CASE WHEN value < 0 THEN 1 ELSE 0 END) AS negative_count
        FROM metrics.fact_values
        WHERE metric_id = :calc_id
        """
        df = read_table(engine, query, params={"calc_id": calc_id})
        metric_counts[calc_code] = int(df[0, "row_count"] or 0)
        negative_counts[calc_code] = int(df[0, "negative_count"] or 0)

    has_all_metrics = all(metric_counts[code] > 0 for code in calc_codes)
    has_negative_values = any(negative_counts[code] > 0 for code in calc_codes)

    return AssetCheckResult(
        passed=has_all_metrics and not has_negative_values,
        metadata={
            "metric_counts": metric_counts,
            "negative_counts": negative_counts,
        },
    )
