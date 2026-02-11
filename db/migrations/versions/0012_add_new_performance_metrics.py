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

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision = "0012"
down_revision = "0011_convert_mvs_to_tables"
branch_labels = None
depends_on = None


def upgrade():
    """Create new metrics fact tables with consistent UUID types and constraints."""

    # ========================================================================
    # fact_throughput: Weekly throughput metrics
    # ========================================================================
    op.create_table(
        "fact_throughput",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("week_start_date", sa.Date(), nullable=False),
        sa.Column("week_end_date", sa.Date(), nullable=False),
        sa.Column("issue_type", sa.Text(), nullable=False),
        sa.Column("issues_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_lead_time_days", sa.Numeric(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["clean_jira.projects.id"], ondelete="CASCADE"
        ),
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
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issue_type", sa.Text(), nullable=False),
        sa.Column("total_issues", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_weeks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_weekly_throughput", sa.Numeric(), nullable=True),
        sa.Column("min_weekly", sa.Integer(), nullable=True),
        sa.Column("max_weekly", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["clean_jira.projects.id"], ondelete="CASCADE"
        ),
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
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("status_name", sa.Text(), nullable=False),
        sa.Column("status_category", sa.Text(), nullable=True),
        sa.Column("issue_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("column_position", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["clean_jira.projects.id"], ondelete="CASCADE"
        ),
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
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status_name", sa.Text(), nullable=False),
        sa.Column("avg_daily_count", sa.Numeric(), nullable=True),
        sa.Column("min_count", sa.Integer(), nullable=True),
        sa.Column("max_count", sa.Integer(), nullable=True),
        sa.Column("trend", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["clean_jira.projects.id"], ondelete="CASCADE"
        ),
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
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "total_backlog_size", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("avg_age_days", sa.Numeric(), nullable=True),
        sa.Column(
            "stale_issues_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("stale_percentage", sa.Numeric(), nullable=True),
        sa.Column("oldest_issue_days", sa.Integer(), nullable=True),
        sa.Column("backlog_growth_last_week", sa.Integer(), nullable=True),
        sa.Column("backlog_growth_last_month", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["clean_jira.projects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("project_id", name="pk_fact_backlog_health"),
        schema="metrics",
    )

    # ========================================================================
    # fact_backlog_distribution: Backlog breakdown by type/priority
    # ========================================================================
    op.create_table(
        "fact_backlog_distribution",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issue_type", sa.Text(), nullable=False),
        sa.Column("priority", sa.Text(), nullable=False),
        sa.Column("issue_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("percentage", sa.Numeric(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["clean_jira.projects.id"], ondelete="CASCADE"
        ),
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
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("age_bucket", sa.Text(), nullable=False),
        sa.Column("issue_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("percentage", sa.Numeric(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["clean_jira.projects.id"], ondelete="CASCADE"
        ),
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
        sa.Column("issue_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issue_key", sa.Text(), nullable=False),
        sa.Column("issue_type", sa.Text(), nullable=False),
        sa.Column("jira_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("time_to_market_days", sa.Numeric(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(
            ["issue_id"], ["clean_jira.issues.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["clean_jira.projects.id"], ondelete="CASCADE"
        ),
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
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issue_type", sa.Text(), nullable=False),
        sa.Column("total_issues", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_ttm_days", sa.Numeric(), nullable=True),
        sa.Column("median_ttm_days", sa.Numeric(), nullable=True),
        sa.Column("p90_ttm_days", sa.Numeric(), nullable=True),
        sa.Column("min_ttm", sa.Numeric(), nullable=True),
        sa.Column("max_ttm", sa.Numeric(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["clean_jira.projects.id"], ondelete="CASCADE"
        ),
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
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("total_releases", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_days_between_releases", sa.Numeric(), nullable=True),
        sa.Column("min_gap", sa.Integer(), nullable=True),
        sa.Column("max_gap", sa.Integer(), nullable=True),
        sa.Column("releases_per_month", sa.Numeric(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["clean_jira.projects.id"], ondelete="CASCADE"
        ),
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
