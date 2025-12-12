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
    """Add default Jira project that clean_jira layer references."""
    # Create default "Jira" project in platform.projects
    # This is used by clean_jira.projects as a grouping project
    op.execute(
        text("""
        INSERT INTO platform.projects (
            id,
            owner_user_id,
            tool_integration_id,
            external_key,
            external_id,
            name,
            is_active,
            created_at,
            updated_at
        )
        SELECT
            '00000000-0000-0000-0000-000000000001'::uuid as id,
            u.id as owner_user_id,
            ti.id as tool_integration_id,
            'JIRA' as external_key,
            'jira-default' as external_id,
            'Jira' as name,
            true as is_active,
            now() as created_at,
            now() as updated_at
        FROM platform.users u
        JOIN platform.tool_integrations ti ON u.id = ti.user_id
        WHERE u.email = 'system@metrics.local'
          AND ti.integration_type_id = (
              SELECT id FROM platform.integration_types WHERE name = 'jira_cloud'
          )
        LIMIT 1
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
