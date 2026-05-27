"""
Backlog Growth Metrics Dagster Asset (Generic Long Metric Store)
"""

from typing import Any

import polars as pl
from dagster import AssetCheckResult, AssetExecutionContext, asset, asset_check

from pipelines.calculations import backlog_growth as backlog_logic
from pipelines.calculations.slicing_utils import get_slice_rules, iter_slicing_results
from pipelines.resources.database import DatabaseResource
from pipelines.utils.metric_registry import (
    get_calculation_id,
    get_definition_id,
    get_project_agg_id,
)
from pipelines.utils.polars_db import read_table, write_fact_values


@asset(
    group_name="metrics",
    deps=[
        "clean_jira_issues",
        "clean_jira_issue_statuses",
        "clean_jira_issue_types",
        "clean_jira_field_values",
        "clean_jira_field_keys",
        "clean_jira_issue_status_changelog",
        "clean_jira_board_column_statuses",
    ],
    description="Calculate Backlog Growth facts and write to generic fact_values",
    metadata={
        "grain": "mixed",
        "unit": "mixed",
        "calculation_logic": "See asset implementation and referenced calculation modules.",
    },
    compute_kind="python",
)
def calculate_backlog_growth(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    engine = database.get_engine()

    def _norm_utf8(df: pl.DataFrame, cols: list[str]) -> pl.DataFrame:
        out = df
        for c in cols:
            if c not in out.columns:
                continue
            if out.schema.get(c) == pl.Object:
                out = out.with_columns(
                    pl.col(c)
                    .map_elements(
                        lambda x: str(x) if x is not None else None,
                        return_dtype=pl.Utf8,
                    )
                    .alias(c)
                )
            else:
                out = out.with_columns(pl.col(c).cast(pl.Utf8, strict=False).alias(c))
        return out

    def _maybe_calc_id(code: str) -> str | None:
        try:
            return get_calculation_id(engine, code)
        except Exception:
            return None

    # 1. Resolve metadata
    def_id = get_definition_id(engine, "backlog_growth")
    calc_map: dict[str, str] = {}

    required = {
        "total_backlog_size": "backlog_size",
        "created_daily": "backlog_created",
        "closed_daily": "backlog_resolved",
        "net_growth_daily": "backlog_net_growth",
    }
    for source_col, code in required.items():
        calc_map[source_col] = str(get_calculation_id(engine, code))

    optional = {
        "avg_age_days": "backlog_avg_age_days",
        "stale_issues_count": "backlog_stale_count",
        "oldest_issue_days": "backlog_oldest_days",
        "stale_percentage": "backlog_stale_pct",
    }
    for source_col, code in optional.items():
        maybe_id = _maybe_calc_id(code)
        if maybe_id:
            calc_map[source_col] = str(maybe_id)

    metric_ids = list(calc_map.values())

    context.log.info("Loading project list for backlog growth...")
    projects_df = read_table(
        engine,
        "SELECT DISTINCT project_id FROM clean_jira.issues WHERE project_id IS NOT NULL",
    )
    if projects_df.is_empty():
        return {"status": "skipped", "reason": "No issues found"}

    field_keys_df = read_table(
        engine,
        "SELECT id, external_key, name FROM clean_jira.field_keys",
    )

    total_rows_written = 0
    projects_processed = 0

    for project_id in projects_df["project_id"].to_list():
        context.log.info(f"Backlog growth batch project_id={project_id}")
        issues_df = read_table(
            engine,
            """
            SELECT i.id, i.project_id, i.type_id, i.status_id,
                   i.jira_created_at, i.jira_updated_at, i.jira_resolved_at
            FROM clean_jira.issues i
            WHERE i.project_id = :project_id
            """,
            params={"project_id": project_id},
        )
        if issues_df.is_empty():
            continue

        issue_statuses_df = read_table(
            engine,
            """
            SELECT id, project_id, name, category
            FROM clean_jira.issue_statuses
            WHERE project_id = :project_id
            """,
            params={"project_id": project_id},
        )
        issue_types_df = read_table(
            engine,
            """
            SELECT id, project_id, name, hierarchy_level
            FROM clean_jira.issue_types
            WHERE project_id = :project_id
            """,
            params={"project_id": project_id},
        )
        issues_df = _norm_utf8(issues_df, ["id", "project_id", "type_id", "status_id"])
        issue_types_df = _norm_utf8(issue_types_df, ["id", "project_id"])
        field_values_df = read_table(
            engine,
            """
            SELECT fv.issue_id, fv.field_key_id, fv.json_value::text AS json_value
            FROM clean_jira.field_values fv
            JOIN clean_jira.issues i ON i.id = fv.issue_id
            WHERE i.project_id = :project_id
            """,
            params={"project_id": project_id},
        )
        changelog_df = read_table(
            engine,
            """
            SELECT isc.issue_id, isc.from_status_id, isc.to_status_id, isc.changed_at
            FROM clean_jira.issue_status_changelog isc
            JOIN clean_jira.issues i ON i.id = isc.issue_id
            WHERE i.project_id = :project_id
            """,
            params={"project_id": project_id},
        )
        board_column_statuses_df = read_table(
            engine,
            """
            SELECT b.project_id, bc.position, bcs.status_id
            FROM clean_jira.board_column_statuses bcs
            JOIN clean_jira.board_columns bc ON bcs.board_column_id = bc.id
            JOIN clean_jira.boards b ON bc.board_id = b.id
            WHERE b.project_id = :project_id
            """,
            params={"project_id": project_id},
        )

        project_agg_id = str(get_project_agg_id(engine, project_id))
        project_agg_map = {str(project_id): project_agg_id}

        health_wide = backlog_logic.calculate_backlog_growth(
            issues_df=issues_df,
            issue_statuses_df=issue_statuses_df,
            field_values_df=field_values_df,
            field_keys_df=field_keys_df,
            changelog_df=changelog_df,
            board_column_statuses_df=board_column_statuses_df,
            days_back=90,
            stale_threshold_days=30,
        )
        if health_wide.is_empty():
            continue
        health_wide = health_wide.with_columns(
            (pl.col("created_daily") - pl.col("closed_daily")).alias("net_growth_daily")
        )

        def transform_to_fact_values(
            df_wide: pl.DataFrame,
            slice_rule_id=None,
            slice_value_col=None,
            _project_agg_map=project_agg_map,
        ) -> pl.DataFrame:
            value_vars = [col for col in calc_map if col in df_wide.columns]
            if not value_vars:
                return pl.DataFrame()
            melted = df_wide.melt(
                id_vars=["project_id", "fact_date"]
                + ([slice_value_col] if slice_value_col else []),
                value_vars=value_vars,
                variable_name="calc_source",
                value_name="value",
            )
            mapped = melted.with_columns(
                [
                    pl.col("calc_source").replace(calc_map).alias("metric_id"),
                    pl.col("project_id")
                    .cast(pl.Utf8)
                    .replace(_project_agg_map)
                    .alias("project_agg_id"),
                    pl.col("fact_date")
                    .dt.strftime("%Y%m%d")
                    .cast(pl.Int32)
                    .alias("time_id"),
                    pl.lit(None).cast(pl.Utf8).alias("entity_type"),
                    pl.lit(None).cast(pl.Utf8).alias("entity_id"),
                    pl.lit(slice_rule_id).cast(pl.Utf8).alias("slice_rule_id"),
                    (
                        pl.col(slice_value_col).cast(pl.Utf8).alias("slice_value")
                        if slice_value_col
                        else pl.lit(None).cast(pl.Utf8).alias("slice_value")
                    ),
                    pl.lit(None).cast(pl.Utf8).alias("commitment_rule_id"),
                    pl.lit(None).cast(pl.Datetime("us", "UTC")).alias("event_start_at"),
                    pl.lit(None).cast(pl.Datetime("us", "UTC")).alias("event_end_at"),
                ]
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

        base_facts = transform_to_fact_values(health_wide)
        if not base_facts.is_empty():
            total_rows_written += write_fact_values(
                base_facts,
                engine,
                metric_ids=metric_ids,
                project_agg_ids=[project_agg_id],
                time_id_start=base_facts["time_id"].min(),
                time_id_end=base_facts["time_id"].max(),
            )

        rules_df = get_slice_rules(
            engine, project_id=project_id, target_definition_id=def_id
        )
        issues_with_type = issues_df.join(
            issue_types_df.select(["id", "name"]),
            left_on="type_id",
            right_on="id",
            how="left",
            coalesce=True,
        ).rename({"name": "issue_type"})

        def health_slice_calc(
            df_subset: pl.DataFrame,
            _field_values_df=field_values_df,
            _changelog_df=changelog_df,
            _issue_statuses_df=issue_statuses_df,
            _board_column_statuses_df=board_column_statuses_df,
        ) -> pl.DataFrame:
            subset_ids = df_subset.select("id")
            subset_field_values = _field_values_df.join(
                subset_ids, left_on="issue_id", right_on="id"
            )
            subset_changelog = _changelog_df.join(
                subset_ids, left_on="issue_id", right_on="id"
            )
            res = backlog_logic.calculate_backlog_growth(
                issues_df=df_subset,
                issue_statuses_df=_issue_statuses_df,
                field_values_df=subset_field_values,
                field_keys_df=field_keys_df,
                changelog_df=subset_changelog,
                board_column_statuses_df=_board_column_statuses_df,
                days_back=90,
                stale_threshold_days=30,
            )
            if not res.is_empty():
                res = res.with_columns(
                    (pl.col("created_daily") - pl.col("closed_daily")).alias(
                        "net_growth_daily"
                    )
                )
            return res

        if not rules_df.is_empty():
            for rule in rules_df.to_dicts():
                rule_id = rule["slice_rule_id"]
                for sliced_wide in iter_slicing_results(
                    issues_with_type,
                    rules_df.filter(pl.col("slice_rule_id") == rule_id),
                    health_slice_calc,
                    engine=engine,
                ):
                    sliced_wide = sliced_wide.filter(
                        (pl.col("total_backlog_size") > 0)
                        | (pl.col("created_daily") > 0)
                        | (pl.col("closed_daily") > 0)
                    )
                    if sliced_wide.is_empty():
                        continue
                    facts = transform_to_fact_values(
                        sliced_wide,
                        slice_rule_id=rule_id,
                        slice_value_col="slice_value",
                    )
                    if not facts.is_empty():
                        total_rows_written += write_fact_values(
                            facts,
                            engine,
                            metric_ids=metric_ids,
                            project_agg_ids=[project_agg_id],
                            time_id_start=facts["time_id"].min(),
                            time_id_end=facts["time_id"].max(),
                        )
        projects_processed += 1

    return {
        "status": "success",
        "rows_written": total_rows_written,
        "projects_processed": projects_processed,
        "metric_ids": metric_ids,
    }


@asset_check(asset=calculate_backlog_growth)
def backlog_growth_data_quality_check(database: DatabaseResource) -> AssetCheckResult:
    engine = database.get_engine()
    calc_id = get_calculation_id(engine, "backlog_size")

    query = "SELECT COUNT(*) FROM metrics.fact_values WHERE metric_id = :calc_id"
    df = read_table(engine, query, params={"calc_id": calc_id})
    count = df[0, 0]

    return AssetCheckResult(passed=count > 0, metadata={"row_count": count})
