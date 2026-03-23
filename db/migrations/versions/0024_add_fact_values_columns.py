"""add_fact_values_columns

Revision ID: 0024
Revises: 0023
Create Date: 2026-03-20

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add columns to metrics.fact_values
    op.add_column(
        "fact_values",
        sa.Column("settings_id", sa.UUID(), nullable=True),
        schema="metrics",
    )
    op.add_column(
        "fact_values",
        sa.Column(
            "context_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        schema="metrics",
    )

    # 2. Add foreign key
    op.create_foreign_key(
        "fk_fact_values_settings",
        "fact_values",
        "calculation_settings",
        ["settings_id"],
        ["id"],
        source_schema="metrics",
        referent_schema="metrics",
        ondelete="SET NULL",
    )

    # 3. Add GIN index
    op.create_index(
        "idx_fact_values_context_gin",
        "fact_values",
        ["context_json"],
        unique=False,
        schema="metrics",
        postgresql_using="gin",
        postgresql_where=sa.text("context_json IS NOT NULL"),
    )

    # 4. Drop and recreate v_facts
    op.execute("DROP VIEW IF EXISTS metrics.v_facts CASCADE")
    op.execute(
        """
        CREATE VIEW metrics.v_facts AS
        SELECT
            fv.id,
            fv.metric_id,
            fv.project_agg_id,
            fv.time_id,
            fv.value,
            fv.entity_type,
            fv.entity_id,
            fv.event_start_at,
            fv.event_end_at,
            fv.slice_rule_id,
            fv.slice_value,
            fv.commitment_rule_id,
            fv.settings_id,
            fv.context_json,
            fv.created_at,
            fv.updated_at,
            c.calc_code,
            c.unit_code,
            c.uses_commitment_points,
            d.metric_code,
            g.grain_code,
            dp.project_key,
            dt.full_date,
            dt.week_num,
            dt.month_num,
            dt.quarter,
            dt.year,
            sr.rule_name AS slice_rule_name,
            cs.settings_type AS calc_settings_type,
            cs.settings_json AS calc_settings_json
        FROM metrics.fact_values fv
        JOIN metrics.calculations c ON fv.metric_id = c.id
        JOIN metrics.definitions d ON c.definition_id = d.id
        JOIN metrics.grains g ON c.grain_id = g.id
        JOIN metrics.dim_projects dp ON fv.project_agg_id = dp.id
        JOIN metrics.dim_dates dt ON fv.time_id = dt.time_id
        LEFT JOIN metrics.slice_rules sr ON fv.slice_rule_id = sr.id
        LEFT JOIN metrics.calculation_settings cs ON fv.settings_id = cs.id
        """
    )


def downgrade():
    # Drop view first because it depends on columns
    op.execute("DROP VIEW IF EXISTS metrics.v_facts CASCADE")

    # Remove index and foreign key
    op.drop_index(
        "idx_fact_values_context_gin", table_name="fact_values", schema="metrics"
    )
    op.drop_constraint(
        "fk_fact_values_settings", "fact_values", schema="metrics", type_="foreignkey"
    )

    # Remove columns
    op.drop_column("fact_values", "context_json", schema="metrics")
    op.drop_column("fact_values", "settings_id", schema="metrics")

    # Recreate original v_facts (as of 0022)
    op.execute(
        """
        CREATE VIEW metrics.v_facts AS
        SELECT
            fv.id,
            fv.metric_id,
            fv.project_agg_id,
            fv.time_id,
            fv.value,
            fv.entity_type,
            fv.entity_id,
            fv.event_start_at,
            fv.event_end_at,
            fv.slice_rule_id,
            fv.slice_value,
            fv.commitment_rule_id,
            fv.created_at,
            fv.updated_at,
            c.calc_code,
            c.unit_code,
            c.uses_commitment_points,
            d.metric_code,
            g.grain_code,
            dp.project_key,
            dt.full_date,
            dt.week_num,
            dt.month_num,
            dt.quarter,
            dt.year,
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
