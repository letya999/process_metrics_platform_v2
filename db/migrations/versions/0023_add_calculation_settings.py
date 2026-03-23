"""add_calculation_settings

Revision ID: 0023
Revises: 0022
Create Date: 2026-03-20

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0023"
down_revision = "0022_fix_v_facts_columns"
branch_labels = None
depends_on = None


def upgrade():
    # Create metrics.calculation_settings table
    op.create_table(
        "calculation_settings",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("target_calculation_id", sa.UUID(), nullable=False),
        sa.Column("settings_type", sa.Text(), nullable=False),
        sa.Column(
            "settings_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
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
            ["project_id"], ["clean_jira.projects.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["target_calculation_id"], ["metrics.calculations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="metrics",
    )

    # Indexes
    op.create_index(
        "idx_calc_settings_project",
        "calculation_settings",
        ["project_id"],
        unique=False,
        schema="metrics",
    )
    op.create_index(
        "idx_calc_settings_calc",
        "calculation_settings",
        ["target_calculation_id"],
        unique=False,
        schema="metrics",
    )

    # Unique partial constraints
    op.create_index(
        "idx_calc_settings_project_type_unique",
        "calculation_settings",
        ["project_id", "target_calculation_id", "settings_type"],
        unique=True,
        schema="metrics",
        postgresql_where=sa.text("project_id IS NOT NULL"),
    )
    op.create_index(
        "idx_calc_settings_type_unique",
        "calculation_settings",
        ["target_calculation_id", "settings_type"],
        unique=True,
        schema="metrics",
        postgresql_where=sa.text("project_id IS NULL"),
    )


def downgrade():
    op.drop_table("calculation_settings", schema="metrics")
