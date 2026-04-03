"""
Flow Efficiency Metrics Dagster Asset (Generic Long Metric Store)
"""

import ast
import json
import logging
from typing import Any

import polars as pl
from dagster import AssetCheckResult, AssetExecutionContext, asset, asset_check

from pipelines.calculations import flow_efficiency as flow_logic
from pipelines.calculations.slicing_utils import apply_slicing, get_slice_rules
from pipelines.resources.database import DatabaseResource
from pipelines.utils.metric_registry import (
    get_calculation_id,
    get_definition_id,
    get_project_agg_id,
)
from pipelines.utils.polars_db import read_table, write_fact_values

logger = logging.getLogger(__name__)


@asset(
    group_name="metrics",
    deps=[
        "clean_jira_issues",
        "clean_jira_issue_types",
        "clean_jira_issue_statuses",
        "clean_jira_issue_status_changelog",
    ],
    description="Calculate Flow Efficiency facts and write to generic fact_values",
    metadata={
        "grain": "mixed",
        "unit": "mixed",
        "calculation_logic": "See asset implementation and referenced calculation modules.",
    },
    compute_kind="python",
)
def calculate_flow_efficiency(
    context: AssetExecutionContext,
    database: DatabaseResource,
) -> dict[str, Any]:
    engine = database.get_engine()

    # 1. Resolve metadata
    def_id = get_definition_id(engine, "flow_efficiency")
    settings_calc_id = get_calculation_id(engine, "flow_efficiency_pct")
    flow_map = {
        "active_days": get_calculation_id(engine, "flow_active_days"),
        "wait_days": get_calculation_id(engine, "flow_wait_days"),
        "efficiency_pct": get_calculation_id(engine, "flow_efficiency_pct"),
    }
    metric_ids = list(flow_map.values())

    context.log.info("Loading data for Flow Efficiency metrics...")

    issues_df = read_table(
        engine,
        """
        SELECT i.id, i.project_id, i.external_key AS key, it.name AS type_name,
               i.status_id, i.jira_created_at, p.external_key AS project_key
        FROM clean_jira.issues i
        JOIN clean_jira.projects p ON i.project_id = p.id
        LEFT JOIN clean_jira.issue_types it ON i.type_id = it.id
        """,
    )

    if issues_df.is_empty():
        return {"status": "skipped", "reason": "No issues found"}

    # Map project_agg_ids
    project_ids = issues_df["project_id"].unique().to_list()
    project_agg_map = {pid: get_project_agg_id(engine, pid) for pid in project_ids}

    status_changelog_df = read_table(
        engine,
        "SELECT issue_id, from_status_id, to_status_id, changed_at FROM clean_jira.issue_status_changelog",
    )

    issue_statuses_df = read_table(
        engine, "SELECT id, project_id, name, category FROM clean_jira.issue_statuses"
    )

    # Load per-project flow status category settings — no hardcode, no fallback
    flow_settings_df = read_table(
        engine,
        "SELECT project_id, settings_json FROM metrics.calculation_settings"
        " WHERE target_calculation_id = :calc_id AND settings_type = 'flow_status_categories' AND enabled = true",
        params={"calc_id": settings_calc_id},
    )

    # 2. Calculate BASE Flow Efficiency facts — per project
    project_ids = issues_df["project_id"].unique().to_list()
    # Build per-project status maps for use in base calc and slice calc
    project_status_maps: dict = {}
    all_flow_wide = []

    for p_id in project_ids:
        p_settings = flow_settings_df.filter(pl.col("project_id") == p_id)
        if p_settings.is_empty():
            context.log.warning(
                f"No flow_status_categories settings for project {p_id} — skipping"
            )
            continue

        cfg = p_settings[0, "settings_json"]
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except json.JSONDecodeError:
                cfg = ast.literal_eval(cfg)
        p_statuses = issue_statuses_df.filter(pl.col("project_id") == p_id)

        # Preferred mode: explicit status-id lists (board/column-level mapping).
        active_ids_cfg = cfg.get("active_status_ids")
        passive_ids_cfg = cfg.get("passive_status_ids")
        done_ids_cfg = cfg.get("done_status_ids")

        if (
            isinstance(active_ids_cfg, list)
            and isinstance(passive_ids_cfg, list)
            and isinstance(done_ids_cfg, list)
        ):
            known_status_ids = set(p_statuses["id"].to_list())
            active_ids = [sid for sid in active_ids_cfg if sid in known_status_ids]
            wait_ids = [sid for sid in passive_ids_cfg if sid in known_status_ids]
            end_ids = [sid for sid in done_ids_cfg if sid in known_status_ids]
        else:
            # Backward-compatible mode: category-based mapping.
            active_cats = cfg.get("active_categories", [])
            passive_cats = cfg.get("passive_categories", [])
            done_cats = cfg.get("done_categories", [])
            active_ids = p_statuses.filter(pl.col("category").is_in(active_cats))[
                "id"
            ].to_list()
            wait_ids = p_statuses.filter(pl.col("category").is_in(passive_cats))[
                "id"
            ].to_list()
            end_ids = p_statuses.filter(pl.col("category").is_in(done_cats))[
                "id"
            ].to_list()

        project_status_maps[p_id] = (active_ids, wait_ids, end_ids)

        p_issues = issues_df.filter(pl.col("project_id") == p_id)
        p_changelog = status_changelog_df.filter(
            pl.col("issue_id").is_in(p_issues["id"].to_list())
        )

        p_flow = flow_logic.calculate_flow_efficiency_per_issue(
            issues_df=p_issues,
            status_changelog_df=p_changelog,
            active_status_ids=active_ids,
            wait_status_ids=wait_ids,
            end_status_ids=end_ids,
        )
        if not p_flow.is_empty():
            all_flow_wide.append(p_flow)

    if not all_flow_wide:
        return {"status": "no_data"}

    flow_wide = pl.concat(all_flow_wide)

    # 3. Transform to Long Format (fact_values)
    def transform_to_fact_values(
        df_wide, slice_rule_id=None, slice_value_col=None, slice_value=None
    ):
        if df_wide.is_empty():
            return pl.DataFrame()

        melted_flow = df_wide.melt(
            id_vars=["project_id", "issue_key", "completion_date"]
            + ([slice_value_col] if slice_value_col else []),
            value_vars=["active_days", "wait_days", "efficiency_pct"],
            variable_name="calc_source",
            value_name="value",
        )

        facts = melted_flow.with_columns(
            [
                pl.col("calc_source").replace(flow_map).alias("metric_id"),
                pl.col("project_id").replace(project_agg_map).alias("project_agg_id"),
                # completion date -> time_id (YYYYMMDD)
                pl.col("completion_date")
                .dt.strftime("%Y%m%d")
                .cast(pl.Int32)
                .alias("time_id"),
                pl.lit("issue").alias("entity_type"),
                pl.col("issue_key").alias("entity_id"),
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
                pl.col("completion_date")
                .cast(pl.Datetime("us", "UTC"))
                .alias("event_end_at"),
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
            ]
        ).drop_nulls(subset=["value"])

    base_facts = transform_to_fact_values(flow_wide)

    # 4. Calculate Sliced facts
    rules_df = get_slice_rules(engine, target_definition_id=def_id)

    # Slicing source: use type_name alias for default rule compatibility
    issues_for_slicing = issues_df.with_columns(pl.col("type_name").alias("issue_type"))

    def flow_slice_calc(df_subset):
        # Sliced subsets may span multiple projects — loop per project and concat
        subset_ids = df_subset["id"].unique().to_list()
        sub_changelog = status_changelog_df.filter(pl.col("issue_id").is_in(subset_ids))
        sub_results = []
        for p_id, (active_ids, wait_ids, end_ids) in project_status_maps.items():
            p_subset = df_subset.filter(pl.col("project_id") == p_id)
            if p_subset.is_empty():
                continue
            p_sub_changelog = sub_changelog.filter(
                pl.col("issue_id").is_in(p_subset["id"].to_list())
            )
            r = flow_logic.calculate_flow_efficiency_per_issue(
                issues_df=p_subset,
                status_changelog_df=p_sub_changelog,
                active_status_ids=active_ids,
                wait_status_ids=wait_ids,
                end_status_ids=end_ids,
            )
            if not r.is_empty():
                sub_results.append(r)
        return pl.concat(sub_results) if sub_results else pl.DataFrame()

    all_facts = [base_facts]

    if not rules_df.is_empty():
        for rule in rules_df.to_dicts():
            rule_id = rule["slice_rule_id"]
            sliced_wide = apply_slicing(
                issues_for_slicing,
                rules_df.filter(pl.col("slice_rule_id") == rule_id),
                flow_slice_calc,
                engine=engine,
            )

            if not sliced_wide.is_empty():
                facts = transform_to_fact_values(
                    sliced_wide, slice_rule_id=rule_id, slice_value_col="slice_value"
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
        "issues_processed": len(flow_wide),
        "metric_ids": metric_ids,
    }


@asset_check(asset=calculate_flow_efficiency)
def flow_efficiency_data_quality_check(database: DatabaseResource) -> AssetCheckResult:
    engine = database.get_engine()
    calc_id = get_calculation_id(engine, "flow_efficiency_pct")

    query = "SELECT COUNT(*) FROM metrics.fact_values WHERE metric_id = :calc_id"
    df = read_table(engine, query, params={"calc_id": calc_id})
    count = df[0, 0]

    return AssetCheckResult(passed=count > 0, metadata={"row_count": count})
