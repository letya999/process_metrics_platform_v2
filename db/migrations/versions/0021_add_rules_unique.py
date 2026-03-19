"""add rules unique

Revision ID: 0021_add_rules_unique
Revises: 0020_seed_metadata
Create Date: 2026-03-19 13:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0021_add_rules_unique"
down_revision = "0020_seed_metadata"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Clean up duplicates first
    op.execute(
        """
        DELETE FROM metrics.slice_rules a USING metrics.slice_rules b
        WHERE a.id < b.id
          AND COALESCE(a.project_id::text, '') = COALESCE(b.project_id::text, '')
          AND a.rule_name = b.rule_name;
        """
    )
    op.execute(
        """
        DELETE FROM metrics.commitment_rules a USING metrics.commitment_rules b
        WHERE a.id < b.id
          AND COALESCE(a.project_id::text, '') = COALESCE(b.project_id::text, '')
          AND COALESCE(a.board_id::text, '') = COALESCE(b.board_id::text, '')
          AND a.target_calculation_id = b.target_calculation_id;
        """
    )

    # 2. Add constraints
    op.create_unique_constraint(
        "uq_slice_rules_project_name",
        "slice_rules",
        ["project_id", "rule_name"],
        schema="metrics",
    )
    # Partial unique for global rules (project_id IS NULL)
    op.create_index(
        "idx_slice_rules_global_unique",
        "slice_rules",
        ["rule_name"],
        unique=True,
        schema="metrics",
        postgresql_where=sa.text("project_id IS NULL"),
    )

    op.create_unique_constraint(
        "uq_commitment_rules_project_board_calc",
        "commitment_rules",
        ["project_id", "board_id", "target_calculation_id"],
        schema="metrics",
    )
    # Partial unique for global commitment rules (if applicable, but they usually have project/board)
    op.create_index(
        "idx_commitment_rules_global_unique",
        "commitment_rules",
        ["board_id", "target_calculation_id"],
        unique=True,
        schema="metrics",
        postgresql_where=sa.text("project_id IS NULL"),
    )


def downgrade():
    op.drop_index(
        "idx_commitment_rules_global_unique",
        table_name="commitment_rules",
        schema="metrics",
    )
    op.drop_constraint(
        "uq_commitment_rules_project_board_calc", "commitment_rules", schema="metrics"
    )
    op.drop_index(
        "idx_slice_rules_global_unique", table_name="slice_rules", schema="metrics"
    )
    op.drop_constraint("uq_slice_rules_project_name", "slice_rules", schema="metrics")
