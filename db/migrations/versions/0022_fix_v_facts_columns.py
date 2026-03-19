"""fix_v_facts_columns

Revision ID: 0022_fix_v_facts_columns
Revises: 0021_add_rules_unique
Create Date: 2026-03-19 19:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0022_fix_v_facts_columns"
down_revision = "0021_add_rules_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS metrics.v_facts")
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


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS metrics.v_facts")
    op.execute(
        """
        CREATE VIEW metrics.v_facts AS
        SELECT
            fv.id,
            fv.value,
            fv.entity_type,
            fv.entity_id,
            fv.event_start_at,
            fv.event_end_at,
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
