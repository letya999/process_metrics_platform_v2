"""Add unique index on (tool_integration_id, external_key) for fast project lookup.

Revision ID: 0032
Revises: 0031
Create Date: 2026-03-28
"""

from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Unique constraint: one project key per integration instance
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_integration_external_key
        ON platform.projects (tool_integration_id, external_key)
        WHERE tool_integration_id IS NOT NULL;
        """
    )

    # Deterministic ordering for _get_platform_project_id fallback
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_projects_created_at
        ON platform.projects (created_at)
        WHERE is_active = true;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS platform.idx_projects_integration_external_key;")
    op.execute("DROP INDEX IF EXISTS platform.idx_projects_created_at;")
