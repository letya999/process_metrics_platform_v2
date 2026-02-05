import logging
from datetime import datetime, timedelta
from typing import List, Tuple

import polars as pl
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from sqlalchemy import text

from pipelines.calculations import (
    aging,
    control_chart,
    cumulative_flow,
    flow_efficiency,
    lead_time,
    lead_time_trend,
)
from pipelines.utils import polars_db


# @anchor:dag:metrics_advanced:get_projects
def get_projects(**kwargs) -> List[Tuple[str, str]]:
    """Get list of projects to process."""
    pg = PostgresHook(postgres_conn_id="postgres_default")
    conf = (kwargs.get("dag_run") or {}).conf or {}
    filter_keys = conf.get("project_keys") if isinstance(conf, dict) else None

    if filter_keys and not isinstance(filter_keys, list):
        filter_keys = [filter_keys]

    base_sql = """
        SELECT id::text, external_key
        FROM projects
        WHERE 1=1
    """
    params = []
    if filter_keys:
        placeholders = ",".join(["%s"] * len(filter_keys))
        if all(isinstance(k, str) and len(k) == 36 and "-" in k for k in filter_keys):
            base_sql += f" AND id IN ({placeholders})"
        else:
            base_sql += f" AND external_key IN ({placeholders})"
        params.extend(filter_keys)

    base_sql += " ORDER BY external_key"
    rows = pg.get_records(base_sql, parameters=tuple(params) if params else None)

    if not rows:
        logging.warning("No projects found for advanced metrics recalculation")
    else:
        logging.info(f"Selected {len(rows)} projects: {[r[1] for r in rows]}")

    kwargs["ti"].xcom_push(key="projects", value=rows)
    return rows


# @anchor:dag:metrics_advanced:recalc_one
def recalc_advanced_metrics_for_project(project: Tuple[str, str]):
    project_id, project_key = project
    logging.info(
        f"Recalculating advanced metrics for project {project_key} ({project_id})"
    )

    pg_hook = PostgresHook(postgres_conn_id="postgres_default")
    engine = pg_hook.get_sqlalchemy_engine()

    # 1. Fetch Raw Data
    logging.info("Fetching raw data...")

    # Issues
    issues_query = """
        SELECT
            i.id, i.project_id, i.key, i.summary, i.type_id, i.current_status_id,
            it.name AS type_name,
            i.created AS jira_created_at,
            i.resolved AS jira_resolved_at
        FROM issues i
        LEFT JOIN issue_types it ON it.id = i.type_id
        WHERE i.project_id = %(project_id)s
    """
    issues_df = polars_db.read_table(
        engine, issues_query, params={"project_id": project_id}
    )

    # Changelog
    changelog_query = """
        SELECT
            h.issue_id, h.from_status_id, h.to_status_id, h.changed_at
        FROM issue_status_history h
        JOIN issues i ON i.id = h.issue_id
        WHERE i.project_id = %(project_id)s
    """
    changelog_df = polars_db.read_table(
        engine, changelog_query, params={"project_id": project_id}
    )

    # Statuses
    statuses_query = """
        SELECT id, project_id, name, category
        FROM statuses
        WHERE project_id = %(project_id)s
    """
    statuses_df = polars_db.read_table(
        engine, statuses_query, params={"project_id": project_id}
    )

    # Boards & Columns
    boards_query = """
        SELECT id, project_id, name
        FROM boards
        WHERE project_id = %(project_id)s
    """
    boards_df = polars_db.read_table(
        engine, boards_query, params={"project_id": project_id}
    )

    # Note: We take all columns for all boards in project
    # If multiple boards exist, calculations might need refinement (currently assumes one unified flow or aggregates)
    columns_query = """
        SELECT bc.id, bc.board_id, bc.name, bc.order_num as position, bcs.status_id
        FROM board_columns bc
        JOIN boards b ON b.id = bc.board_id
        JOIN board_column_statuses bcs ON bcs.board_column_id = bc.id
        WHERE b.project_id = %(project_id)s
    """
    columns_df = polars_db.read_table(
        engine, columns_query, params={"project_id": project_id}
    )

    if issues_df.is_empty():
        logging.warning(f"No issues found for project {project_key}")
        return

    # 2. Cleanup Old Data
    logging.info("Cleaning up old calc results...")
    cleanup_tables = [
        "fact_work_item_aging",
        "fact_flow_efficiency",
        "fact_control_chart",
        "fact_lead_time_trend",
        "fact_cumulative_flow",
    ]
    with engine.connect() as conn:
        for table in cleanup_tables:
            conn.execute(
                text(
                    f"DELETE FROM metrics.{table} WHERE project_id = :pid"  # noqa: S608
                ),
                {"pid": project_id},
            )
        conn.commit()

    # 3. Calculate & Write Aging
    logging.info("Calculating Aging...")
    aging_df = aging.calculate_aging_work(
        issues_df, changelog_df, boards_df, columns_df
    )
    if not aging_df.is_empty():
        polars_db.write_table(
            aging_df, engine, "fact_work_item_aging", if_exists="append"
        )

    # 4. Calculate & Write Flow Efficiency
    logging.info("Calculating Flow Efficiency...")
    # Smart guess for wait statuses: 'Blocked', 'On Hold'
    # (In a real app, this should be config-driven)
    wait_status_ids = []
    if not statuses_df.is_empty():
        wait_df = statuses_df.filter(
            pl.col("name").str.to_lowercase().str.contains("blocked")
            | pl.col("name").str.to_lowercase().str.contains("hold")
            | pl.col("name").str.to_lowercase().str.contains("wait")
        )
        wait_status_ids = wait_df["id"].to_list() if "id" in wait_df.columns else []

    efficiency_df = flow_efficiency.calculate_flow_efficiency(
        issues_df, changelog_df, boards_df, columns_df, wait_status_ids=wait_status_ids
    )
    if not efficiency_df.is_empty():
        polars_db.write_table(
            efficiency_df, engine, "fact_flow_efficiency", if_exists="append"
        )

    # 5. Calculate Lead Time (needed for Control Chart & Trends)
    # We recalc in-memory to ensure consistency
    lt_df = lead_time.calculate_lead_time_facts(
        issues_df, changelog_df, boards_df, columns_df
    )

    # 6. Calculate & Write Control Chart
    logging.info("Calculating Control Chart...")
    if not lt_df.is_empty():
        cc_df = control_chart.calculate_control_chart_stats(lt_df)
        if not cc_df.is_empty():
            # Keep only columns present in target table
            # [id, project_id, issue_id, commitment_end_at, lead_time_days, rolling_mean, rolling_std, ucl_2sigma, ucl_3sigma, is_outlier]
            # control_chart.py returns merged with input, so we have project_id, issue_id etc.
            # Make sure to select correct columns for DB write
            cc_write = cc_df.select(
                [
                    "project_id",
                    "issue_id",
                    "commitment_end_at",
                    "lead_time_days",
                    "rolling_mean",
                    "rolling_std",
                    "ucl_2sigma",
                    "ucl_3sigma",
                    "is_outlier",
                ]
            )
            polars_db.write_table(
                cc_write, engine, "fact_control_chart", if_exists="append"
            )

    # 7. Calculate & Write Lead Time Trends
    logging.info("Calculating Lead Time Trends...")
    if not lt_df.is_empty():
        trend_df = lead_time_trend.calculate_lead_time_trends(lt_df, period="1w")
        if not trend_df.is_empty():
            # Add project_id and period_type
            trend_write = trend_df.with_columns(
                [
                    pl.lit(project_id).alias("project_id"),
                    pl.lit("weekly").alias("period_type"),
                ]
            )
            polars_db.write_table(
                trend_write, engine, "fact_lead_time_trend", if_exists="append"
            )

    # 8. Calculate & Write Cumulative Flow
    logging.info("Calculating CFD...")
    cfd_df = cumulative_flow.calculate_cumulative_flow_diagram(
        issues_df, changelog_df, statuses_df, boards_df, columns_df, days_back=90
    )
    if not cfd_df.is_empty():
        polars_db.write_table(
            cfd_df, engine, "fact_cumulative_flow", if_exists="append"
        )

    logging.info(f"Advanced metrics update complete for {project_key}")


def recalc_all(**kwargs):
    ti = kwargs["ti"]
    projects = ti.xcom_pull(key="projects", task_ids="get_projects") or []
    if not projects:
        logging.warning("No projects to process")
        return

    for p in projects:
        try:
            recalc_advanced_metrics_for_project(p)
        except Exception as e:
            logging.exception("Failed to recalc stats for project %s: %s", p, e)
            continue


with DAG(
    "metrics_advanced_recalculate",
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,
    catchup=False,
    tags=["metrics", "facts", "advanced"],
    default_args={
        "retries": 1,
        "retry_delay": timedelta(minutes=1),
    },
    description="Recalculate Pro metrics: Aging, Flow Efficiency, Control Chart, Trends",
) as dag:
    t_get = PythonOperator(task_id="get_projects", python_callable=get_projects)
    t_recalc = PythonOperator(
        task_id="recalculate_advanced", python_callable=recalc_all
    )

    t_get >> t_recalc
