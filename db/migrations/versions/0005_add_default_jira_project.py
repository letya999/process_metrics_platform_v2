"""Add default Jira platform project for clean layer

Revision ID: 0005_add_default_jira_project
Revises: 0004_add_system_user
Create Date: 2025-12-12
"""

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "0005_add_default_jira_project"
down_revision = "0004_add_system_user"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add default Jira platform project for clean_jira layer.

    This system project acts as a grouping container for all Jira data
    in the clean layer. It doesn't require an owner or integration reference.
    """
    op.execute(
        text("""
        INSERT INTO platform.projects (
            id,
            external_key,
            external_id,
            name,
            is_active,
            created_at,
            updated_at
        )
        VALUES (
            '00000000-0000-0000-0000-000000000001'::uuid,
            'JIRA',
            'jira-system',
            'Jira System Project',
            true,
            now(),
            now()
        )
        ON CONFLICT (id) DO NOTHING;
    """)
    )


def downgrade() -> None:
    """Rollback: Remove default Jira project."""
    op.execute(
        text("""
        DELETE FROM platform.projects
        WHERE id = '00000000-0000-0000-0000-000000000001'::uuid;
    """)
    )
