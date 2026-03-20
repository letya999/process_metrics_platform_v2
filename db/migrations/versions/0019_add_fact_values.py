"""add_fact_values_and_view

Revision ID: 0019
Revises: 0018
Create Date: 2026-03-19 11:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0019_add_fact_values"
down_revision = "0018_add_metric_store_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. metrics.fact_values
    op.create_table(
        "fact_values",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("metric_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_agg_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("time_id", sa.Integer(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),  # DOUBLE PRECISION
        sa.Column("entity_type", sa.Text(), nullable=True),
        sa.Column("entity_id", sa.Text(), nullable=True),
        sa.Column("event_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("event_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("slice_rule_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("slice_value", sa.Text(), nullable=True),
        sa.Column("commitment_rule_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["metric_id"], ["metrics.calculations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["project_agg_id"], ["metrics.dim_projects.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["time_id"], ["metrics.dim_dates.time_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["slice_rule_id"], ["metrics.slice_rules.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["commitment_rule_id"], ["metrics.commitment_rules.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="metrics",
    )

    # 2. Indexes
    op.create_index(
        "idx_fact_values_main",
        "fact_values",
        ["metric_id", "project_agg_id", "time_id"],
        postgresql_include=["value", "slice_value", "entity_id", "entity_type"],
        schema="metrics",
    )
    op.create_index(
        "idx_fact_values_project_time",
        "fact_values",
        ["project_agg_id", "time_id"],
        postgresql_include=["value", "metric_id"],
        schema="metrics",
    )
    op.create_index(
        "idx_fact_values_base",
        "fact_values",
        ["metric_id", "project_agg_id", "time_id"],
        postgresql_where=sa.text("slice_rule_id IS NULL"),
        schema="metrics",
    )
    op.create_index(
        "idx_fact_values_entity",
        "fact_values",
        ["entity_type", "entity_id"],
        postgresql_where=sa.text("entity_id IS NOT NULL"),
        schema="metrics",
    )

    # 3. Create view metrics.v_facts
    op.execute(
        """
        CREATE OR REPLACE VIEW metrics.v_facts AS
        SELECT
            fv.id, fv.value, fv.entity_type, fv.entity_id,
            fv.event_start_at, fv.event_end_at,
            fv.slice_value, fv.commitment_rule_id,
            fv.created_at, fv.updated_at,
            c.calc_code, c.unit_code, c.uses_commitment_points,
            d.metric_code,
            g.grain_code,
            dp.project_key,
            dt.full_date, dt.week_num, dt.month_num, dt.quarter, dt.year,
            sr.rule_name AS slice_rule_name
        FROM metrics.fact_values fv
        JOIN metrics.calculations c ON fv.metric_id = c.id
        JOIN metrics.definitions d ON c.definition_id = d.id
        JOIN metrics.grains g ON c.grain_id = g.id
        JOIN metrics.dim_projects dp ON fv.project_agg_id = dp.id
        JOIN metrics.dim_dates dt ON fv.time_id = dt.time_id
        LEFT JOIN metrics.slice_rules sr ON fv.slice_rule_id = sr.id
    """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS metrics.v_facts")
    op.drop_table("fact_values", schema="metrics")
