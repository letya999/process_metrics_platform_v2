"""add_all_metrics_slices

Revision ID: 0015
Revises: 0014
Create Date: 2026-02-18 10:30:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Update metric_slice_rules table structure
    # Use generic execute for renames to handle potential idempotency if already renamed (though usually migration runs once)
    # We assume clean state from 0014.

    # Check if column 'metric' exists before renaming (idempotency check conceptually, but plain alembic assumes strict state)
    # We'll just run the renames.
    op.execute(
        "ALTER TABLE metrics.metric_slice_rules RENAME COLUMN metric TO target_metric_table"
    )
    op.execute(
        "ALTER TABLE metrics.metric_slice_rules RENAME COLUMN slice_dim TO rule_name"
    )

    op.add_column(
        "metric_slice_rules",
        sa.Column("slice_table_name", sa.Text(), nullable=True),
        schema="metrics",
    )
    op.add_column(
        "metric_slice_rules",
        sa.Column("source_table", sa.Text(), nullable=True),
        schema="metrics",
    )
    op.add_column(
        "metric_slice_rules",
        sa.Column("group_by_column", sa.Text(), nullable=True),
        schema="metrics",
    )
    op.add_column(
        "metric_slice_rules",
        sa.Column("filter_condition", sa.Text(), nullable=True),
        schema="metrics",
    )

    # Add Global Default Rule
    op.execute(
        """
        INSERT INTO metrics.metric_slice_rules
        (target_metric_table, rule_name, source_table, group_by_column, enabled)
        VALUES
        ('default', 'By Issue Type', 'clean_jira.issue_types', 'name', true)
    """
    )

    # 2. Drop old singular tables if they exist (cleanup)
    old_tables = [
        "fact_velocity_slice",
        "fact_lead_time_slice",
        "fact_lead_time_bins_slice",
        "fact_throughput_slice",
        "fact_time_to_market_slice",
        "fact_backlog_growth_slice",
        "fact_flow_efficiency_slice",
        "fact_work_item_aging_slice",
    ]
    for table in old_tables:
        op.execute(f"DROP TABLE IF EXISTS metrics.{table} CASCADE")

    # 3. Create new PLURAL slice tables (_slices)

    # fact_velocity_slices (Aggregated by Sprint)
    op.create_table(
        "fact_velocity_slices",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sprint_id", sa.Text(), nullable=True),
        sa.Column("slice_rule_name", sa.Text(), nullable=False),
        sa.Column("slice_value", sa.Text(), nullable=False),
        sa.Column("planned_points", sa.Numeric(), default=0),
        sa.Column("completed_points", sa.Numeric(), default=0),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["clean_jira.projects.id"], ondelete="CASCADE"
        ),
        schema="metrics",
    )

    # fact_throughput_slices (Aggregated by Week)
    op.create_table(
        "fact_throughput_slices",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slice_rule_name", sa.Text(), nullable=False),
        sa.Column("slice_value", sa.Text(), nullable=False),
        sa.Column("completed_date", sa.Date(), nullable=False),
        sa.Column("issues_completed", sa.Integer(), default=0),
        sa.Column("avg_lead_time_days", sa.Numeric(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["clean_jira.projects.id"], ondelete="CASCADE"
        ),
        schema="metrics",
    )

    # fact_backlog_growth_slices (Aggregated by Period)
    op.create_table(
        "fact_backlog_growth_slices",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slice_rule_name", sa.Text(), nullable=False),
        sa.Column("slice_value", sa.Text(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_type", sa.Text(), server_default="weekly"),
        sa.Column("created_count", sa.Integer(), default=0),
        sa.Column("completed_count", sa.Integer(), default=0),
        sa.Column("net_growth", sa.Integer(), default=0),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["clean_jira.projects.id"], ondelete="CASCADE"
        ),
        schema="metrics",
    )

    # fact_lead_time_slices (Per Issue - Granular)
    op.create_table(
        "fact_lead_time_slices",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "issue_id", sa.Text(), nullable=True
        ),  # Using Text to avoid strict UUID checks if source varies, but normally UUID.
        sa.Column("issue_key", sa.Text(), nullable=False),
        sa.Column("commitment_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("commitment_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lead_time_days", sa.Numeric(), nullable=True),
        sa.Column("slice_rule_name", sa.Text(), nullable=False),
        sa.Column("slice_value", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["clean_jira.projects.id"], ondelete="CASCADE"
        ),
        schema="metrics",
    )

    # fact_time_to_market_slices (Per Issue - Granular)
    op.create_table(
        "fact_time_to_market_slices",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issue_id", sa.Text(), nullable=True),
        sa.Column("issue_key", sa.Text(), nullable=False),
        sa.Column("jira_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("time_to_market_days", sa.Numeric(), nullable=True),
        sa.Column("slice_rule_name", sa.Text(), nullable=False),
        sa.Column("slice_value", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["clean_jira.projects.id"], ondelete="CASCADE"
        ),
        schema="metrics",
    )

    # fact_flow_efficiency_slices (Per Issue - Granular)
    op.create_table(
        "fact_flow_efficiency_slices",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issue_id", sa.Text(), nullable=True),
        sa.Column("issue_key", sa.Text(), nullable=False),
        sa.Column("active_time_days", sa.Numeric(), nullable=True),
        sa.Column("waiting_time_days", sa.Numeric(), nullable=True),
        sa.Column("efficiency_pct", sa.Numeric(), nullable=True),
        sa.Column("slice_rule_name", sa.Text(), nullable=False),
        sa.Column("slice_value", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["clean_jira.projects.id"], ondelete="CASCADE"
        ),
        schema="metrics",
    )

    # fact_work_item_aging_slices (Per Issue - Granular)
    op.create_table(
        "fact_work_item_aging_slices",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issue_id", sa.Text(), nullable=True),
        sa.Column("issue_key", sa.Text(), nullable=False),
        sa.Column("age_days", sa.Numeric(), nullable=True),
        sa.Column("current_status", sa.Text(), nullable=True),
        sa.Column("slice_rule_name", sa.Text(), nullable=False),
        sa.Column("slice_value", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["clean_jira.projects.id"], ondelete="CASCADE"
        ),
        schema="metrics",
    )


def downgrade() -> None:
    # Drop all slice tables
    tables = [
        "fact_work_item_aging_slices",
        "fact_flow_efficiency_slices",
        "fact_time_to_market_slices",
        "fact_lead_time_slices",
        "fact_backlog_growth_slices",
        "fact_throughput_slices",
        "fact_velocity_slices",
    ]
    for table in tables:
        op.drop_table(table, schema="metrics")

    # Revert rule table changes
    op.execute(
        "DELETE FROM metrics.metric_slice_rules WHERE target_metric_table = 'default'"
    )
    op.drop_column("metrics.metric_slice_rules", "filter_condition")
    op.drop_column("metrics.metric_slice_rules", "group_by_column")
    op.drop_column("metrics.metric_slice_rules", "source_table")
    op.drop_column("metrics.metric_slice_rules", "slice_table_name")
    op.execute(
        "ALTER TABLE metrics.metric_slice_rules RENAME COLUMN rule_name TO slice_dim"
    )
    op.execute(
        "ALTER TABLE metrics.metric_slice_rules RENAME COLUMN target_metric_table TO metric"
    )
