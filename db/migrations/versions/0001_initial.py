"""Initial empty revision (baseline).

Revision ID: 0001_initial
Revises: None
Create Date: 2025-10-17
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Baseline migration: Create core platform and raw_jira schemas/tables.
    This ensures that subsequent migrations (0002+) can safely reference them."""

    # Enable pgcrypto for UUID generation
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

    # Create schemas
    op.execute("CREATE SCHEMA IF NOT EXISTS platform;")
    op.execute("CREATE SCHEMA IF NOT EXISTS raw_jira;")

    # ============================================================================
    # Platform Core Entities
    # ============================================================================

    # Enums
    op.execute(
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'external_tool_type') THEN CREATE TYPE platform.external_tool_type AS ENUM ('metabase', 'superset', 'grafana'); END IF; END $$;"
    )
    op.execute(
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'external_tool_role') THEN CREATE TYPE platform.external_tool_role AS ENUM ('admin', 'editor', 'viewer'); END IF; END $$;"
    )
    op.execute(
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'integration_type_enum') THEN CREATE TYPE platform.integration_type_enum AS ENUM ('jira_cloud', 'jira_server', 'jira_datacenter', 'linear', 'asana', 'github', 'gitlab'); END IF; END $$;"
    )
    op.execute(
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'project_access_level') THEN CREATE TYPE platform.project_access_level AS ENUM ('owner', 'admin', 'viewer'); END IF; END $$;"
    )

    # Tables
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS platform.users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT true,
            is_admin BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_password_change TIMESTAMPTZ
        );
    """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS platform.integration_types (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name platform.integration_type_enum UNIQUE NOT NULL,
            description TEXT,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS platform.tool_integrations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES platform.users(id) ON DELETE CASCADE,
            integration_type_id UUID NOT NULL REFERENCES platform.integration_types(id),
            instance_url TEXT,
            user_email TEXT,
            secret_reference TEXT,
            secret_provider TEXT DEFAULT 'env',
            api_token_unsafe TEXT,
            api_token_expires_at TIMESTAMPTZ,
            api_token_expired BOOLEAN DEFAULT FALSE NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT true,
            last_sync_at TIMESTAMPTZ,
            last_sync_status TEXT,
            last_error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(user_id, integration_type_id, instance_url)
        );
    """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS platform.projects (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id UUID REFERENCES platform.users(id) ON DELETE SET NULL,
            tool_integration_id UUID REFERENCES platform.tool_integrations(id) ON DELETE SET NULL,
            external_key TEXT NOT NULL,
            external_id TEXT NOT NULL,
            name TEXT NOT NULL,
            external_url TEXT,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS platform.audit_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID REFERENCES platform.users(id) ON DELETE SET NULL,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id UUID,
            details JSONB,
            ip_address INET,
            user_agent TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """
    )

    # Populate base integration types
    op.execute(
        """
        INSERT INTO platform.integration_types (name, description) VALUES
            ('jira_cloud', 'Jira Cloud integration'),
            ('jira_server', 'Jira Server integration (self-hosted)'),
            ('jira_datacenter', 'Jira Data Center integration (self-hosted)'),
            ('linear', 'Linear integration'),
            ('asana', 'Asana integration'),
            ('github', 'GitHub integration'),
            ('gitlab', 'GitLab integration')
        ON CONFLICT (name) DO NOTHING;
    """
    )


def downgrade() -> None:
    """Rollback: Drop schemas and all contents."""
    op.execute("DROP SCHEMA IF EXISTS platform CASCADE;")
    op.execute("DROP SCHEMA IF EXISTS raw_jira CASCADE;")
