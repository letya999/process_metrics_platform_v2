"""Add new performance metrics tables

Revision ID: 0012
Revises: 0011
Create Date: 2026-01-31

This migration adds fact tables for new performance metrics:
- fact_throughput (weekly throughput)
- fact_cfd (cumulative flow diagram)
- fact_backlog_health (backlog health metrics)
- fact_time_to_market (time to market metrics)
- fact_release_cadence (release frequency)
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    """Create new metrics fact tables."""

    # ========================================================================
    # fact_throughput: Weekly throughput metrics
    # ========================================================================
    op.create_table(
        "fact_throughput",
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("week_start_date", sa.Date(), nullable=False),
        sa.Column("week_end_date", sa.Date(), nullable=False),
        sa.Column("issue_type", sa.String(), nullable=False),
        sa.Column("issues_completed", sa.BigInteger(), nullable=False),
        sa.Column("avg_lead_time_days", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint(
            "project_id", "week_start_date", "issue_type", name="pk_fact_throughput"
        ),
        schema="metrics",
    )
    op.create_index(
        "idx_fact_throughput_project_week",
        "fact_throughput",
        ["project_id", "week_start_date"],
        schema="metrics",
    )

    # ========================================================================
    # fact_throughput_aggregates: Throughput summary statistics
    # ========================================================================
    op.create_table(
        "fact_throughput_aggregates",
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("issue_type", sa.String(), nullable=False),
        sa.Column("total_issues", sa.BigInteger(), nullable=False),
        sa.Column("total_weeks", sa.BigInteger(), nullable=False),
        sa.Column("avg_weekly_throughput", sa.Float(), nullable=True),
        sa.Column("min_weekly", sa.BigInteger(), nullable=True),
        sa.Column("max_weekly", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint(
            "project_id", "issue_type", name="pk_fact_throughput_aggregates"
        ),
        schema="metrics",
    )

    # ========================================================================
    # fact_cfd: Cumulative Flow Diagram data
    # ========================================================================
    op.create_table(
        "fact_cfd",
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("status_name", sa.String(), nullable=False),
        sa.Column("status_category", sa.String(), nullable=True),
        sa.Column("issue_count", sa.BigInteger(), nullable=False),
        sa.Column("column_position", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint(
            "project_id", "date", "status_name", name="pk_fact_cfd"
        ),
        schema="metrics",
    )
    op.create_index(
        "idx_fact_cfd_project_date",
        "fact_cfd",
        ["project_id", "date"],
        schema="metrics",
    )

    # ========================================================================
    # fact_cfd_aggregates: CFD summary statistics
    # ========================================================================
    op.create_table(
        "fact_cfd_aggregates",
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("status_name", sa.String(), nullable=False),
        sa.Column("avg_daily_count", sa.Float(), nullable=True),
        sa.Column("min_count", sa.BigInteger(), nullable=True),
        sa.Column("max_count", sa.BigInteger(), nullable=True),
        sa.Column("trend", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint(
            "project_id", "status_name", name="pk_fact_cfd_aggregates"
        ),
        schema="metrics",
    )

    # ========================================================================
    # fact_backlog_health: Backlog health metrics
    # ========================================================================
    op.create_table(
        "fact_backlog_health",
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("total_backlog_size", sa.BigInteger(), nullable=False),
        sa.Column("avg_age_days", sa.Float(), nullable=True),
        sa.Column("stale_issues_count", sa.BigInteger(), nullable=False),
        sa.Column("stale_percentage", sa.Float(), nullable=True),
        sa.Column("oldest_issue_days", sa.BigInteger(), nullable=True),
        sa.Column("backlog_growth_last_week", sa.BigInteger(), nullable=True),
        sa.Column("backlog_growth_last_month", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("project_id", name="pk_fact_backlog_health"),
        schema="metrics",
    )

    # ========================================================================
    # fact_backlog_distribution: Backlog breakdown by type/priority
    # ========================================================================
    op.create_table(
        "fact_backlog_distribution",
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("issue_type", sa.String(), nullable=False),
        sa.Column("priority", sa.String(), nullable=False),
        sa.Column("issue_count", sa.BigInteger(), nullable=False),
        sa.Column("percentage", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint(
            "project_id", "issue_type", "priority", name="pk_fact_backlog_distribution"
        ),
        schema="metrics",
    )

    # ========================================================================
    # fact_backlog_age_distribution: Age distribution of backlog
    # ========================================================================
    op.create_table(
        "fact_backlog_age_distribution",
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("age_bucket", sa.String(), nullable=False),
        sa.Column("issue_count", sa.BigInteger(), nullable=False),
        sa.Column("percentage", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint(
            "project_id", "age_bucket", name="pk_fact_backlog_age_distribution"
        ),
        schema="metrics",
    )

    # ========================================================================
    # fact_time_to_market: Time to Market metrics
    # ========================================================================
    op.create_table(
        "fact_time_to_market",
        sa.Column("issue_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("issue_key", sa.String(), nullable=False),
        sa.Column("issue_type", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("time_to_market_days", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("issue_id", name="pk_fact_time_to_market"),
        schema="metrics",
    )
    op.create_index(
        "idx_fact_ttm_project_released",
        "fact_time_to_market",
        ["project_id", "released_at"],
        schema="metrics",
    )

    # ========================================================================
    # fact_ttm_aggregates: TTM summary statistics
    # ========================================================================
    op.create_table(
        "fact_ttm_aggregates",
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("issue_type", sa.String(), nullable=False),
        sa.Column("total_issues", sa.BigInteger(), nullable=False),
        sa.Column("avg_ttm_days", sa.Float(), nullable=True),
        sa.Column("median_ttm_days", sa.Float(), nullable=True),
        sa.Column("p90_ttm_days", sa.Float(), nullable=True),
        sa.Column("min_ttm", sa.Float(), nullable=True),
        sa.Column("max_ttm", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint(
            "project_id", "issue_type", name="pk_fact_ttm_aggregates"
        ),
        schema="metrics",
    )

    # ========================================================================
    # fact_release_cadence: Release frequency metrics
    # ========================================================================
    op.create_table(
        "fact_release_cadence",
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("total_releases", sa.BigInteger(), nullable=False),
        sa.Column("avg_days_between_releases", sa.Float(), nullable=True),
        sa.Column("min_gap", sa.BigInteger(), nullable=True),
        sa.Column("max_gap", sa.BigInteger(), nullable=True),
        sa.Column("releases_per_month", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("project_id", name="pk_fact_release_cadence"),
        schema="metrics",
    )


def downgrade():
    """Drop new metrics fact tables."""

    op.drop_table("fact_release_cadence", schema="metrics")
    op.drop_table("fact_ttm_aggregates", schema="metrics")
    op.drop_index(
        "idx_fact_ttm_project_released",
        table_name="fact_time_to_market",
        schema="metrics",
    )
    op.drop_table("fact_time_to_market", schema="metrics")
    op.drop_table("fact_backlog_age_distribution", schema="metrics")
    op.drop_table("fact_backlog_distribution", schema="metrics")
    op.drop_table("fact_backlog_health", schema="metrics")
    op.drop_table("fact_cfd_aggregates", schema="metrics")
    op.drop_index("idx_fact_cfd_project_date", table_name="fact_cfd", schema="metrics")
    op.drop_table("fact_cfd", schema="metrics")
    op.drop_table("fact_throughput_aggregates", schema="metrics")
    op.drop_index(
        "idx_fact_throughput_project_week",
        table_name="fact_throughput",
        schema="metrics",
    )
    op.drop_table("fact_throughput", schema="metrics")
