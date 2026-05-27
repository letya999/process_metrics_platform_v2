"""
Cumulative Flow Diagram (CFD) Dagster Asset (Generic Long Metric Store).
"""

import os
from typing import Any

import polars as pl
from dagster import AssetCheckResult, AssetExecutionContext, asset, asset_check

from pipelines.calculations import cumulative_flow as cfd_logic
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
        "clean_jira_boards",
        "clean_jira_board_columns",
        "clean_jira_issue_status_changelog",
    ],
    description="Calculate CFD facts and write to generic fact_values",
    metadata={
        "grain": "mixed",
        "unit": "mixed",
        "calculation_logic": "See asset implementation and referenced calculation modules.",
    },
    compute_kind="python",
)
def calculate_cumulative_flow_diagram(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    engine = database.get_engine()

    # 1. Resolve metadata
    def_id = get_definition_id(engine, "cfd")
    calc_id = str(get_calculation_id(engine, "cfd_count"))

    context.log.info("Loading project list for CFD...")

    projects_df = read_table(
        engine,
        """
        SELECT DISTINCT i.project_id
        FROM clean_jira.issues i
        WHERE i.project_id IS NOT NULL
        """,
    )
    if projects_df.is_empty():
        return {"status": "skipped", "reason": "No issues found"}

    issue_statuses_df = read_table(
        engine,
        "SELECT id, project_id, name, category FROM clean_jira.issue_statuses",
    )
    rules_df = get_slice_rules(engine, target_definition_id=def_id)

    # 2. Calculate BASE CFD facts
    # 3. Transform to Long Format (fact_values)
    def _utf8_expr(df: pl.DataFrame, col: str, alias: str | None = None) -> pl.Expr:
        out = alias or col
        if col not in df.columns:
            return pl.lit(None).cast(pl.Utf8).alias(out)
        if df.schema.get(col) == pl.Object:
            return (
                pl.col(col)
                .map_elements(
                    lambda x: str(x) if x is not None else None,
                    return_dtype=pl.Utf8,
                )
                .alias(out)
            )
        return pl.col(col).cast(pl.Utf8, strict=False).alias(out)

    def transform_to_fact_values(
        df_wide,
        board_columns_df,
        project_agg_id,
        slice_rule_id=None,
        slice_value_col=None,
        slice_value=None,
    ):
        if df_wide.is_empty():
            return pl.DataFrame()

        # Enrich with board column name for better CFD context payload.
        df_enriched = df_wide
        if "column_id" in df_wide.columns and "id" in board_columns_df.columns:
            board_column_names = board_columns_df.select(
                [
                    _utf8_expr(board_columns_df, "id", "column_id"),
                    _utf8_expr(board_columns_df, "name", "column_name"),
                ]
            ).unique(subset=["column_id"], keep="first")
            df_enriched = df_wide.join(
                board_column_names, on="column_id", how="left", coalesce=True
            )

        def _opt_col(name: str, dtype: pl.DataType = pl.Utf8) -> pl.Expr:
            if name in df_enriched.columns:
                if dtype == pl.Utf8 and df_enriched.schema.get(name) == pl.Object:
                    return pl.col(name).map_elements(
                        lambda x: str(x) if x is not None else None,
                        return_dtype=pl.Utf8,
                    )
                return pl.col(name).cast(dtype)
            return pl.lit(None).cast(dtype)

        facts = df_enriched.with_columns(
            [
                pl.lit(str(calc_id)).alias("metric_id"),
                pl.lit(str(project_agg_id)).alias("project_agg_id"),
                pl.col("date").dt.strftime("%Y%m%d").cast(pl.Int32).alias("time_id"),
                pl.col("issue_count").cast(pl.Float64).alias("value"),
                pl.lit("board_column").alias("entity_type"),
                pl.coalesce([pl.col("column_id"), pl.col("status_id")])
                .cast(pl.Utf8)
                .alias("entity_id"),
                pl.lit(slice_rule_id).cast(pl.Utf8).alias("slice_rule_id"),
                (
                    pl.col(slice_value_col).cast(pl.Utf8).alias("slice_value")
                    if slice_value_col
                    else (
                        pl.lit(slice_value).cast(pl.Utf8).alias("slice_value")
                        if slice_value is not None
                        else pl.lit(None).cast(pl.Utf8).alias("slice_value")
                    )
                ),
                pl.lit(None).cast(pl.Utf8).alias("commitment_rule_id"),
                pl.lit(None).cast(pl.Datetime("us", "UTC")).alias("event_start_at"),
                pl.lit(None).cast(pl.Datetime("us", "UTC")).alias("event_end_at"),
                pl.struct(
                    [
                        _opt_col("column_id").alias("column_id"),
                        _opt_col("column_name").alias("column_name"),
                        _opt_col("status_id").alias("status_id"),
                        _opt_col("status_name").alias("status_name"),
                        _opt_col("status_category").alias("status_category"),
                        _opt_col("column_position", pl.Int64).alias("column_position"),
                    ]
                ).alias("context_json"),
            ]
        )

        return facts.select(
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
                "context_json",
            ]
        )

    rows_written_total = 0
    projects_processed = 0
    issue_batch_size = int(os.getenv("CFD_ISSUE_BATCH_SIZE", "4000"))

    def _calc_cfd_batched(
        *,
        issues_df: pl.DataFrame,
        status_changelog_df: pl.DataFrame,
        issue_statuses_df: pl.DataFrame,
        boards_df: pl.DataFrame,
        board_columns_df: pl.DataFrame,
        days_back: int,
    ) -> pl.DataFrame:
        if len(issues_df) > issue_batch_size:
            context.log.info(
                f"CFD issue batching is disabled for stability (issues={len(issues_df)} batch_size={issue_batch_size})"
            )
        return cfd_logic.calculate_cumulative_flow_diagram(
            issues_df=issues_df,
            status_changelog_df=status_changelog_df,
            issue_statuses_df=issue_statuses_df,
            boards_df=boards_df,
            board_columns_df=board_columns_df,
            days_back=days_back,
        )

    for project_id in projects_df["project_id"].to_list():
        context.log.info(f"CFD batch project_id={project_id}")
        issues_df = read_table(
            engine,
            """
            SELECT i.id, i.project_id, it.name as type_name, i.status_id, i.jira_created_at, p.external_key AS project_key
            FROM clean_jira.issues i
            JOIN clean_jira.projects p ON i.project_id = p.id
            LEFT JOIN clean_jira.issue_types it ON i.type_id = it.id
            WHERE i.project_id = :project_id
            """,
            params={"project_id": project_id},
        )
        if issues_df.is_empty():
            continue

        status_changelog_df = read_table(
            engine,
            """
            SELECT isc.issue_id, isc.from_status_id, isc.to_status_id, isc.changed_at
            FROM clean_jira.issue_status_changelog isc
            JOIN clean_jira.issues i ON i.id = isc.issue_id
            WHERE i.project_id = :project_id
            """,
            params={"project_id": project_id},
        )

        boards_df = read_table(
            engine,
            "SELECT id, project_id, name FROM clean_jira.boards WHERE project_id = :project_id",
            params={"project_id": project_id},
        )
        board_columns_df = read_table(
            engine,
            """
            SELECT bc.id, bc.board_id, bc.name, bc.position, bcs.status_id
            FROM clean_jira.board_columns bc
            LEFT JOIN clean_jira.board_column_statuses bcs ON bcs.board_column_id = bc.id
            JOIN clean_jira.boards b ON b.id = bc.board_id
            WHERE b.project_id = :project_id
            """,
            params={"project_id": project_id},
        )

        cfd_wide = _calc_cfd_batched(
            issues_df=issues_df,
            status_changelog_df=status_changelog_df,
            issue_statuses_df=issue_statuses_df,
            boards_df=boards_df,
            board_columns_df=board_columns_df,
            days_back=90,
        )
        if cfd_wide.is_empty():
            continue

        project_agg_id = get_project_agg_id(engine, project_id)
        base_facts = transform_to_fact_values(
            cfd_wide, board_columns_df=board_columns_df, project_agg_id=project_agg_id
        )
        if not base_facts.is_empty():
            rows_written_total += write_fact_values(
                base_facts,
                engine,
                metric_ids=[calc_id],
                project_agg_ids=[project_agg_id],
                time_id_start=base_facts["time_id"].min(),
                time_id_end=base_facts["time_id"].max(),
            )

        issues_for_slicing = issues_df.with_columns(
            pl.col("type_name").alias("issue_type")
        )

        def cfd_slice_calc(
            df_subset,
            *,
            _status_changelog_df=status_changelog_df,
            _issue_statuses_df=issue_statuses_df,
            _boards_df=boards_df,
            _board_columns_df=board_columns_df,
        ):
            if df_subset.schema.get("id") == pl.Object:
                subset_ids = (
                    df_subset.select(
                        pl.col("id")
                        .map_elements(
                            lambda x: str(x) if x is not None else None,
                            return_dtype=pl.Utf8,
                        )
                        .alias("id")
                    )["id"]
                    .unique()
                    .to_list()
                )
            else:
                subset_ids = (
                    df_subset.select(
                        pl.col("id").cast(pl.Utf8, strict=False).alias("id")
                    )["id"]
                    .unique()
                    .to_list()
                )
            subset_series = pl.Series("subset_ids", subset_ids, dtype=pl.Utf8)
            if _status_changelog_df.schema.get("issue_id") == pl.Object:
                sub_changelog = _status_changelog_df.with_columns(
                    pl.col("issue_id")
                    .map_elements(
                        lambda x: str(x) if x is not None else None,
                        return_dtype=pl.Utf8,
                    )
                    .alias("__issue_id_norm")
                )
            else:
                sub_changelog = _status_changelog_df.with_columns(
                    pl.col("issue_id")
                    .cast(pl.Utf8, strict=False)
                    .alias("__issue_id_norm")
                )
            sub_changelog = sub_changelog.filter(
                pl.col("__issue_id_norm").is_in(subset_series)
            ).drop("__issue_id_norm")
            return _calc_cfd_batched(
                issues_df=df_subset,
                status_changelog_df=sub_changelog,
                issue_statuses_df=_issue_statuses_df,
                boards_df=_boards_df,
                board_columns_df=_board_columns_df,
                days_back=90,
            )

        if not rules_df.is_empty():
            for rule in rules_df.to_dicts():
                rule_id = rule["slice_rule_id"]
                for sliced_wide in iter_slicing_results(
                    issues_for_slicing,
                    rules_df.filter(pl.col("slice_rule_id") == rule_id),
                    cfd_slice_calc,
                    engine=engine,
                ):
                    sliced_facts = transform_to_fact_values(
                        sliced_wide,
                        board_columns_df=board_columns_df,
                        project_agg_id=project_agg_id,
                        slice_rule_id=rule_id,
                        slice_value_col="slice_value",
                    )
                    if not sliced_facts.is_empty():
                        rows_written_total += write_fact_values(
                            sliced_facts,
                            engine,
                            metric_ids=[calc_id],
                            project_agg_ids=[project_agg_id],
                            time_id_start=sliced_facts["time_id"].min(),
                            time_id_end=sliced_facts["time_id"].max(),
                        )
        projects_processed += 1

    return {
        "status": "success",
        "rows_written": rows_written_total,
        "projects_processed": projects_processed,
        "metric_ids": [calc_id],
    }


@asset_check(asset=calculate_cumulative_flow_diagram)
def cfd_data_quality_check(database: DatabaseResource) -> AssetCheckResult:
    engine = database.get_engine()
    calc_id = get_calculation_id(engine, "cfd_count")

    query = "SELECT COUNT(*) FROM metrics.fact_values WHERE metric_id = :calc_id"
    df = read_table(engine, query, params={"calc_id": calc_id})
    count = df[0, 0]

    return AssetCheckResult(passed=count > 0, metadata={"row_count": count})
