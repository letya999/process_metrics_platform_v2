"""Add integration_sync_checkpoints table

Revision ID: 0002_add_integration_sync_checkpoints
Revises: 0001_initial
Create Date: 2025-10-20
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0002_sync_checkpoints"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure required extension and schema exist (idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
    op.execute("CREATE SCHEMA IF NOT EXISTS platform;")

    op.create_table(
        "integration_sync_checkpoints",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tool_integration_id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            nullable=False,
        ),
        sa.Column(
            "project_id", sa.dialects.postgresql.UUID(as_uuid=False), nullable=True
        ),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sync_metadata", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(
            ["tool_integration_id"],
            ["platform.tool_integrations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["platform.projects.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "tool_integration_id",
            "project_id",
            "entity_type",
            name="uq_sync_checkpoint_integration_project_entity",
        ),
        schema="platform",
    )

    op.create_index(
        "idx_sync_checkpoints_tool_integration",
        "integration_sync_checkpoints",
        ["tool_integration_id"],
        unique=False,
        schema="platform",
    )
    op.create_index(
        "idx_sync_checkpoints_project",
        "integration_sync_checkpoints",
        ["project_id"],
        unique=False,
        schema="platform",
    )

    # Optional comments for clarity (split for asyncpg prepared statement limitation)
    op.execute(
        "COMMENT ON TABLE platform.integration_sync_checkpoints IS "
        "'Per-resource sync checkpoints for integrations (DLT/Prefect)'"
    )
    op.execute(
        "COMMENT ON COLUMN platform.integration_sync_checkpoints.entity_type IS "
        "'Entity type (e.g., issues_created, issues_updated, sprints)'"
    )


def downgrade() -> None:
    op.drop_index(
        "idx_sync_checkpoints_project",
        table_name="integration_sync_checkpoints",
        schema="platform",
    )
    op.drop_index(
        "idx_sync_checkpoints_tool_integration",
        table_name="integration_sync_checkpoints",
        schema="platform",
    )
    op.drop_table("integration_sync_checkpoints", schema="platform")
