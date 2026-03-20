"""drop_legacy_fact_tables

Revision ID: 0025
Revises: 0024
Create Date: 2026-03-20

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade():
    # Drop views that depend on legacy tables first
    op.execute("DROP VIEW IF EXISTS metrics.mv_velocity CASCADE")
    op.execute("DROP VIEW IF EXISTS metrics.mv_lead_time CASCADE")
    op.execute("DROP VIEW IF EXISTS metrics.mv_throughput CASCADE")

    # Legacy wide fact tables (created in 0011, not dropped in 0014)
    op.execute("DROP TABLE IF EXISTS metrics.fact_velocity CASCADE")
    op.execute("DROP TABLE IF EXISTS metrics.fact_velocity_slice CASCADE")
    op.execute("DROP TABLE IF EXISTS metrics.fact_lead_time CASCADE")

    # Pro metrics tables (created in 0013, dropped in 0014 but some survive)
    op.execute("DROP TABLE IF EXISTS metrics.fact_work_item_aging CASCADE")
    op.execute("DROP TABLE IF EXISTS metrics.fact_flow_efficiency CASCADE")
    op.execute("DROP TABLE IF EXISTS metrics.fact_control_chart CASCADE")
    op.execute("DROP TABLE IF EXISTS metrics.fact_lead_time_trend CASCADE")

    # Slice tables from 0015 (never cleaned up)
    op.execute("DROP TABLE IF EXISTS metrics.fact_velocity_slices CASCADE")
    op.execute("DROP TABLE IF EXISTS metrics.fact_throughput_slices CASCADE")
    op.execute("DROP TABLE IF EXISTS metrics.fact_backlog_growth_slices CASCADE")
    op.execute("DROP TABLE IF EXISTS metrics.fact_lead_time_slices CASCADE")
    op.execute("DROP TABLE IF EXISTS metrics.fact_time_to_market_slices CASCADE")
    op.execute("DROP TABLE IF EXISTS metrics.fact_flow_efficiency_slices CASCADE")
    op.execute("DROP TABLE IF EXISTS metrics.fact_work_item_aging_slices CASCADE")

    # Old slice rules table superseded by metrics.slice_rules (0018)
    op.execute("DROP TABLE IF EXISTS metrics.metric_slice_rules CASCADE")


def downgrade():
    # Downgrade is not supported for this migration as legacy tables are removed
    raise NotImplementedError("Rollback to legacy fact tables is not supported.")
