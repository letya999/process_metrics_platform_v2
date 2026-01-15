"""Add system user and default Jira integration for automated pipelines

Revision ID: 0004_add_system_user
Revises: 0003_metrics_schema
Create Date: 2025-12-12
"""

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "0004_add_system_user"
down_revision = "0003_metrics_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add system user and default Jira integration for pipeline operations."""
    # Create system user if it doesn't exist
    op.execute(
        text(
            """
        INSERT INTO platform.users (email, password_hash, display_name, is_active, is_admin)
        VALUES (
            'system@metrics.local',
            'system',
            'System',
            true,
            true
        )
        ON CONFLICT (email) DO NOTHING;
    """
        )
    )

    # Create default Jira integration type if not exists
    op.execute(
        text(
            """
        INSERT INTO platform.integration_types (name, description, is_active)
        VALUES ('jira_cloud', 'Jira Cloud integration', true)
        ON CONFLICT (name) DO NOTHING;
    """
        )
    )

    # Create system Jira integration for the system user
    op.execute(
        text(
            """
        INSERT INTO platform.tool_integrations (
            user_id,
            integration_type_id,
            instance_url,
            user_email,
            secret_reference,
            secret_provider,
            is_active
        )
        SELECT
            u.id,
            it.id,
            'https://system.atlassian.net',
            'system@metrics.local',
            'JIRA_SYSTEM_TOKEN',
            'env',
            true
        FROM platform.users u, platform.integration_types it
        WHERE u.email = 'system@metrics.local'
          AND it.name = 'jira_cloud'
          AND NOT EXISTS (
              SELECT 1 FROM platform.tool_integrations ti
              WHERE ti.user_id = u.id AND ti.integration_type_id = it.id
          )
        ON CONFLICT (user_id, integration_type_id, instance_url) DO NOTHING;
    """
        )
    )


def downgrade() -> None:
    """Rollback: Remove system user and integration."""
    op.execute(
        text(
            """
        DELETE FROM platform.tool_integrations
        WHERE user_id = (SELECT id FROM platform.users WHERE email = 'system@metrics.local')
          AND integration_type_id = (SELECT id FROM platform.integration_types WHERE name = 'jira_cloud');
    """
        )
    )

    op.execute(
        text(
            """
        DELETE FROM platform.users WHERE email = 'system@metrics.local';
    """
        )
    )
