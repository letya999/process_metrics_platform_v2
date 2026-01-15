"""Add metrics schema with materialized views

Revision ID: 0003_metrics_schema
Revises: 0002_create_clean_jira_schema
Create Date: 2025-12-11
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0003_metrics_schema"
down_revision = "0002_create_clean_jira_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create metrics schema with materialized views."""
    # Create metrics schema
    op.execute("CREATE SCHEMA IF NOT EXISTS metrics;")
    op.execute(
        "COMMENT ON SCHEMA metrics IS "
        "'Materialized views for team metrics (Lead Time, Velocity, Throughput)';"
    )

    # MVs are now created by db/views/metrics.sql after tables are created
    # Check 0006 for fact table creation

    pass
    # MVs and refresh function are now created by db/views/metrics.sql after tables are created
    # Check 0006 for fact table creation


def downgrade() -> None:
    """Drop metrics schema and all its contents."""
    op.execute("DROP SCHEMA IF EXISTS metrics CASCADE;")
