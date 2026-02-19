"""cleanup_metrics_tables

Revision ID: 0014
Revises: 0013
Create Date: 2026-02-18 10:00:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Drop views (if they exist)
    views_to_drop = [
        "mv_lead_time",
        "mv_throughput",
        "mv_velocity",
        "mv_velocity_slice",
        "mv_lead_time_slice",
        "mv_lead_time_bins_slice",
    ]

    for view in views_to_drop:
        op.execute(f"DROP VIEW IF EXISTS metrics.{view} CASCADE")

    # 2. Drop unused tables
    tables_to_drop = [
        "fact_lead_time_trend",
        "fact_control_chart",
        "fact_flow_efficiency",
        "fact_work_item_aging",
        "fact_release_cadence",
        "fact_ttm_aggregates",
        "fact_backlog_age_distribution",
        "fact_backlog_distribution",
        "fact_cfd_aggregates",
        "fact_throughput_aggregates",
        "fact_lead_time_bins_slice",
        "fact_lead_time_bins",
        "fact_lead_time_slice",
    ]

    for table in tables_to_drop:
        op.drop_table(table, schema="metrics")

    # 3. Rename fact_backlog_health to fact_backlog_growth
    op.rename_table("fact_backlog_health", "fact_backlog_growth", schema="metrics")


def downgrade():
    # 1. Rename back
    op.rename_table("fact_backlog_growth", "fact_backlog_health", schema="metrics")

    # 2. Recreating dropped tables is complex and requires copying schema from 0011, 0012, 0013.
    # For now, we raise an error to prevent accidental data loss or require manual restoration.
    raise NotImplementedError(
        "Downgrade for cleanup_metrics_tables is not implemented completely. Restore from backup or previous migrations."
    )
