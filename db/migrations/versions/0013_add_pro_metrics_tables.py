"""Add Pro metrics tables (Aging, Flow Efficiency, Control Chart, Trends)

Revision ID: 0013
Revises: 0012
Create Date: 2026-02-04 18:25:00.000000

This migration adds tables for "Pro" metrics:
- fact_work_item_aging: Current active issues and their age
- fact_flow_efficiency: Active vs Wait time for issues
- fact_control_chart: Daily/Rolling stats for process control
- fact_lead_time_trend: Weekly/Monthly percentile trends
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    """Create Pro metrics tables."""

    # ========================================================================
    # fact_work_item_aging: Current active items snapshot
    # ========================================================================
    op.create_table(
        "fact_work_item_aging",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issue_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issue_key", sa.Text(), nullable=True),
        sa.Column("issue_type", sa.Text(), nullable=True),
        sa.Column("current_status", sa.Text(), nullable=True),
        sa.Column("commitment_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("age_days", sa.Numeric(), nullable=True),
        sa.Column("age_in_status_days", sa.Numeric(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(
            ["issue_id"], ["clean_jira.issues.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["clean_jira.projects.id"], ondelete="CASCADE"
        ),
        schema="metrics",
    )
    op.create_index(
        "idx_aging_project", "fact_work_item_aging", ["project_id"], schema="metrics"
    )

    # ========================================================================
    # fact_flow_efficiency: Active vs Wait time
    # ========================================================================
    op.create_table(
        "fact_flow_efficiency",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issue_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issue_key", sa.Text(), nullable=True),
        sa.Column("issue_type", sa.Text(), nullable=True),
        sa.Column("active_days", sa.Numeric(), nullable=True),
        sa.Column("wait_days", sa.Numeric(), nullable=True),
        sa.Column("total_days", sa.Numeric(), nullable=True),
        sa.Column("flow_efficiency_pct", sa.Numeric(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(
            ["issue_id"], ["clean_jira.issues.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["clean_jira.projects.id"], ondelete="CASCADE"
        ),
        schema="metrics",
    )
    op.create_index(
        "idx_flow_efficiency_project",
        "fact_flow_efficiency",
        ["project_id"],
        schema="metrics",
    )

    # ========================================================================
    # fact_control_chart: Rolling stats for detailed analysis
    # ========================================================================
    op.create_table(
        "fact_control_chart",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issue_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("commitment_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lead_time_days", sa.Numeric(), nullable=True),
        sa.Column("rolling_mean", sa.Numeric(), nullable=True),
        sa.Column("rolling_std", sa.Numeric(), nullable=True),
        sa.Column("ucl_2sigma", sa.Numeric(), nullable=True),
        sa.Column("ucl_3sigma", sa.Numeric(), nullable=True),
        sa.Column("is_outlier", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(
            ["issue_id"], ["clean_jira.issues.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["clean_jira.projects.id"], ondelete="CASCADE"
        ),
        schema="metrics",
    )
    op.create_index(
        "idx_control_chart_project",
        "fact_control_chart",
        ["project_id"],
        schema="metrics",
    )

    # ========================================================================
    # fact_lead_time_trend: Weekly/Monthly trends
    # ========================================================================
    op.create_table(
        "fact_lead_time_trend",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_type", sa.Text(), server_default="weekly"),
        sa.Column("issue_count", sa.Integer(), nullable=True),
        sa.Column("p50", sa.Numeric(), nullable=True),
        sa.Column("p85", sa.Numeric(), nullable=True),
        sa.Column("p95", sa.Numeric(), nullable=True),
        sa.Column("trend_p85", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["clean_jira.projects.id"], ondelete="CASCADE"
        ),
        schema="metrics",
    )
    op.create_index(
        "idx_lt_trend_project", "fact_lead_time_trend", ["project_id"], schema="metrics"
    )


def downgrade():
    """Drop Pro metrics tables."""
    op.drop_table("fact_lead_time_trend", schema="metrics")
    op.drop_table("fact_control_chart", schema="metrics")
    op.drop_table("fact_flow_efficiency", schema="metrics")
    op.drop_table("fact_work_item_aging", schema="metrics")
