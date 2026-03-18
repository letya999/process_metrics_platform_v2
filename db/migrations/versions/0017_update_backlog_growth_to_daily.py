"""update_backlog_growth_to_daily

Revision ID: 0017
Revises: 0016
Create Date: 2026-02-19 14:30:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Update fact_backlog_growth table
    # Drop existing Primary Key constraint
    op.execute(
        "ALTER TABLE metrics.fact_backlog_growth DROP CONSTRAINT IF EXISTS pk_fact_backlog_health"
    )

    # Add fact_date column
    op.add_column(
        "fact_backlog_growth",
        sa.Column(
            "fact_date",
            sa.Date(),
            nullable=False,
            server_default=sa.text("CURRENT_DATE"),
        ),
        schema="metrics",
    )

    # Replace growth columns with daily columns
    op.drop_column("fact_backlog_growth", "backlog_growth_last_week", schema="metrics")
    op.drop_column("fact_backlog_growth", "backlog_growth_last_month", schema="metrics")

    op.add_column(
        "fact_backlog_growth",
        sa.Column("created_daily", sa.Integer(), nullable=False, server_default="0"),
        schema="metrics",
    )
    op.add_column(
        "fact_backlog_growth",
        sa.Column("closed_daily", sa.Integer(), nullable=False, server_default="0"),
        schema="metrics",
    )
    op.add_column(
        "fact_backlog_growth",
        sa.Column(
            "entered_backlog_count", sa.Integer(), nullable=False, server_default="0"
        ),
        schema="metrics",
    )
    op.add_column(
        "fact_backlog_growth",
        sa.Column(
            "exited_backlog_count", sa.Integer(), nullable=False, server_default="0"
        ),
        schema="metrics",
    )

    # Add new Primary Key
    op.create_primary_key(
        "pk_fact_backlog_growth_daily",
        "fact_backlog_growth",
        ["project_id", "fact_date"],
        schema="metrics",
    )

    # 2. Update fact_backlog_growth_slices table
    # It has an 'id' as PK, so we just add/remove columns
    op.add_column(
        "fact_backlog_growth_slices",
        sa.Column(
            "fact_date",
            sa.Date(),
            nullable=False,
            server_default=sa.text("CURRENT_DATE"),
        ),
        schema="metrics",
    )
    op.drop_column(
        "fact_backlog_growth_slices", "backlog_growth_last_week", schema="metrics"
    )
    op.drop_column(
        "fact_backlog_growth_slices", "backlog_growth_last_month", schema="metrics"
    )

    op.add_column(
        "fact_backlog_growth_slices",
        sa.Column("created_daily", sa.Integer(), nullable=False, server_default="0"),
        schema="metrics",
    )
    op.add_column(
        "fact_backlog_growth_slices",
        sa.Column("closed_daily", sa.Integer(), nullable=False, server_default="0"),
        schema="metrics",
    )
    op.add_column(
        "fact_backlog_growth_slices",
        sa.Column(
            "entered_backlog_count", sa.Integer(), nullable=False, server_default="0"
        ),
        schema="metrics",
    )
    op.add_column(
        "fact_backlog_growth_slices",
        sa.Column(
            "exited_backlog_count", sa.Integer(), nullable=False, server_default="0"
        ),
        schema="metrics",
    )


def downgrade():
    # Downgrade logic to revert to previous state
    # This is complex due to PK change, but we can try to restore it
    op.execute(
        "ALTER TABLE metrics.fact_backlog_growth DROP CONSTRAINT IF EXISTS pk_fact_backlog_growth_daily"
    )

    op.drop_column("fact_backlog_growth", "fact_date", schema="metrics")
    op.drop_column("fact_backlog_growth", "created_daily", schema="metrics")
    op.drop_column("fact_backlog_growth", "closed_daily", schema="metrics")
    op.drop_column("fact_backlog_growth", "entered_backlog_count", schema="metrics")
    op.drop_column("fact_backlog_growth", "exited_backlog_count", schema="metrics")

    op.add_column(
        "fact_backlog_growth",
        sa.Column("backlog_growth_last_week", sa.Integer(), nullable=True),
        schema="metrics",
    )
    op.add_column(
        "fact_backlog_growth",
        sa.Column("backlog_growth_last_month", sa.Integer(), nullable=True),
        schema="metrics",
    )

    op.create_primary_key(
        "pk_fact_backlog_health",
        "fact_backlog_growth",
        ["project_id"],
        schema="metrics",
    )

    # Slices revert
    op.drop_column("fact_backlog_growth_slices", "fact_date", schema="metrics")
    op.drop_column("fact_backlog_growth_slices", "created_daily", schema="metrics")
    op.drop_column("fact_backlog_growth_slices", "closed_daily", schema="metrics")
    op.drop_column(
        "fact_backlog_growth_slices", "entered_backlog_count", schema="metrics"
    )
    op.drop_column(
        "fact_backlog_growth_slices", "exited_backlog_count", schema="metrics"
    )

    op.add_column(
        "fact_backlog_growth_slices",
        sa.Column("backlog_growth_last_week", sa.Integer(), nullable=True),
        schema="metrics",
    )
    op.add_column(
        "fact_backlog_growth_slices",
        sa.Column("backlog_growth_last_month", sa.Integer(), nullable=True),
        schema="metrics",
    )
