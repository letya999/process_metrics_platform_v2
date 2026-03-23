"""drop_remaining_legacy_fact_tables

Revision ID: 0027
Revises: 0026
Create Date: 2026-03-21

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Drop main legacy fact tables requested by user (and their descendants/renames)
    op.execute("DROP TABLE IF EXISTS metrics.fact_cfd CASCADE")
    op.execute("DROP TABLE IF EXISTS metrics.fact_backlog_growth CASCADE")
    op.execute("DROP TABLE IF EXISTS metrics.fact_cfd_slices CASCADE")
    op.execute("DROP TABLE IF EXISTS metrics.fact_throughput CASCADE")
    op.execute("DROP TABLE IF EXISTS metrics.fact_time_to_market CASCADE")

    # 2. Drop associated legacy aggregate/distribution tables from 0012/0013
    # These were mostly no longer updated after the move to generic fact store
    op.execute("DROP TABLE IF EXISTS metrics.fact_throughput_aggregates CASCADE")
    op.execute("DROP TABLE IF EXISTS metrics.fact_cfd_aggregates CASCADE")
    op.execute("DROP TABLE IF EXISTS metrics.fact_ttm_aggregates CASCADE")
    op.execute("DROP TABLE IF EXISTS metrics.fact_backlog_health CASCADE")
    op.execute("DROP TABLE IF EXISTS metrics.fact_backlog_distribution CASCADE")
    op.execute("DROP TABLE IF EXISTS metrics.fact_backlog_age_distribution CASCADE")
    op.execute("DROP TABLE IF EXISTS metrics.fact_release_cadence CASCADE")


def downgrade():
    # Downgrade is not supported for this migration as legacy tables are removed
    # and their structure is superseded by metrics.fact_values
    raise NotImplementedError("Rollback to legacy fact tables is not supported.")
