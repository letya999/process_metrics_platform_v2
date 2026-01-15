"""Create clean_jira schema with all tables

Revision ID: 0002_create_clean_jira_schema
Revises: 0001_initial
Create Date: 2025-12-12
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0002_create_clean_jira_schema"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create clean_jira schema with normalized Jira data tables."""
    # Create schema
    op.execute("CREATE SCHEMA IF NOT EXISTS clean_jira;")

    # Create ENUMs (with IF NOT EXISTS check using DO block)
    op.execute(
        """DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'issue_hierarchy_level' AND typnamespace = 'clean_jira'::regnamespace) THEN
                CREATE TYPE clean_jira.issue_hierarchy_level AS ENUM ('epic', 'story', 'task', 'subtask');
            END IF;
        END $$;"""
    )
    op.execute(
        """DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'issue_status_category' AND typnamespace = 'clean_jira'::regnamespace) THEN
                CREATE TYPE clean_jira.issue_status_category AS ENUM ('to_do', 'in_progress', 'done');
            END IF;
        END $$;"""
    )
    op.execute(
        """DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_role_type' AND typnamespace = 'clean_jira'::regnamespace) THEN
                CREATE TYPE clean_jira.user_role_type AS ENUM ('assignee', 'reporter', 'creator', 'watcher');
            END IF;
        END $$;"""
    )
    op.execute(
        """DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'sprint_status' AND typnamespace = 'clean_jira'::regnamespace) THEN
                CREATE TYPE clean_jira.sprint_status AS ENUM ('future', 'active', 'closed');
            END IF;
        END $$;"""
    )
    op.execute(
        """DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'release_status' AND typnamespace = 'clean_jira'::regnamespace) THEN
                CREATE TYPE clean_jira.release_status AS ENUM ('unreleased', 'released', 'archived');
            END IF;
        END $$;"""
    )

    # Create core entity tables
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS clean_jira.projects (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            platform_project_id uuid NOT NULL REFERENCES platform.projects(id) ON DELETE CASCADE,
            external_id text NOT NULL,
            external_key text NOT NULL,
            name text NOT NULL,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            UNIQUE(platform_project_id, external_id),
            UNIQUE(platform_project_id, external_key)
        );
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS clean_jira.issue_types (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id uuid NOT NULL REFERENCES clean_jira.projects(id) ON DELETE CASCADE,
            external_id text NOT NULL,
            name text NOT NULL,
            hierarchy_level clean_jira.issue_hierarchy_level NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE(project_id, external_id),
            UNIQUE(project_id, name)
        );
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS clean_jira.issue_statuses (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id uuid NOT NULL REFERENCES clean_jira.projects(id) ON DELETE CASCADE,
            external_id text NOT NULL,
            name text NOT NULL,
            category clean_jira.issue_status_category NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE(project_id, external_id),
            UNIQUE(project_id, name)
        );
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS clean_jira.jira_users (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id uuid NOT NULL REFERENCES clean_jira.projects(id) ON DELETE CASCADE,
            external_id text NOT NULL,
            display_name text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE(project_id, external_id)
        );
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS clean_jira.issues (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id uuid NOT NULL REFERENCES clean_jira.projects(id) ON DELETE CASCADE,
            external_id text NOT NULL,
            external_key text NOT NULL,
            summary text NOT NULL,
            description text,
            type_id uuid NOT NULL REFERENCES clean_jira.issue_types(id),
            status_id uuid NOT NULL REFERENCES clean_jira.issue_statuses(id),
            parent_id uuid REFERENCES clean_jira.issues(id),
            jira_created_at timestamptz NOT NULL,
            jira_updated_at timestamptz NOT NULL,
            jira_resolved_at timestamptz,
            db_created_at timestamptz NOT NULL DEFAULT now(),
            db_updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE(project_id, external_id),
            UNIQUE(project_id, external_key)
        );
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS clean_jira.jira_user_issue_roles (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES clean_jira.jira_users(id) ON DELETE CASCADE,
            issue_id uuid NOT NULL REFERENCES clean_jira.issues(id) ON DELETE CASCADE,
            role_type clean_jira.user_role_type NOT NULL,
            assigned_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE(user_id, issue_id, role_type)
        );
        """
    )

    # Create sprint tables
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS clean_jira.sprints (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id uuid NOT NULL REFERENCES clean_jira.projects(id) ON DELETE CASCADE,
            external_id text NOT NULL,
            name text NOT NULL,
            goal text,
            status clean_jira.sprint_status NOT NULL,
            start_date timestamptz,
            end_date timestamptz,
            complete_date timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE(project_id, external_id)
        );
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS clean_jira.sprint_issues (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            sprint_id uuid NOT NULL REFERENCES clean_jira.sprints(id) ON DELETE CASCADE,
            issue_id uuid NOT NULL REFERENCES clean_jira.issues(id) ON DELETE CASCADE,
            is_active boolean NOT NULL DEFAULT true,
            UNIQUE(sprint_id, issue_id)
        );
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS clean_jira.sprint_issues_changelog (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            sprint_id uuid NOT NULL REFERENCES clean_jira.sprints(id) ON DELETE CASCADE,
            issue_id uuid NOT NULL REFERENCES clean_jira.issues(id) ON DELETE CASCADE,
            action text NOT NULL CHECK (action IN ('added', 'removed')),
            changed_by_id uuid REFERENCES clean_jira.jira_users(id),
            changed_at timestamptz NOT NULL,
            UNIQUE(sprint_id, issue_id, action, changed_at)
        );
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS clean_jira.sprint_changelog (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            sprint_id uuid NOT NULL REFERENCES clean_jira.sprints(id) ON DELETE CASCADE,
            field_name text NOT NULL,
            old_value text,
            new_value text,
            changed_by_id uuid REFERENCES clean_jira.jira_users(id),
            changed_at timestamptz NOT NULL
        );
        """
    )

    # Create release tables
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS clean_jira.releases (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id uuid NOT NULL REFERENCES clean_jira.projects(id) ON DELETE CASCADE,
            external_id text NOT NULL,
            name text NOT NULL,
            description text,
            status clean_jira.release_status NOT NULL,
            start_date date,
            release_date date,
            is_archived boolean NOT NULL DEFAULT false,
            is_released boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE(project_id, external_id)
        );
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS clean_jira.release_issues (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            release_id uuid NOT NULL REFERENCES clean_jira.releases(id) ON DELETE CASCADE,
            issue_id uuid NOT NULL REFERENCES clean_jira.issues(id) ON DELETE CASCADE,
            is_active boolean NOT NULL DEFAULT true,
            UNIQUE(release_id, issue_id)
        );
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS clean_jira.release_issues_changelog (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            release_id uuid NOT NULL REFERENCES clean_jira.releases(id) ON DELETE CASCADE,
            issue_id uuid NOT NULL REFERENCES clean_jira.issues(id) ON DELETE CASCADE,
            action text NOT NULL CHECK (action IN ('added', 'removed')),
            changed_by_id uuid REFERENCES clean_jira.jira_users(id),
            changed_at timestamptz NOT NULL,
            UNIQUE(release_id, issue_id, action, changed_at)
        );
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS clean_jira.release_changelog (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            release_id uuid NOT NULL REFERENCES clean_jira.releases(id) ON DELETE CASCADE,
            field_name text NOT NULL,
            old_value text,
            new_value text,
            changed_by_id uuid REFERENCES clean_jira.jira_users(id),
            changed_at timestamptz NOT NULL
        );
        """
    )

    # Create custom field tables
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS clean_jira.field_keys (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id uuid NOT NULL REFERENCES clean_jira.projects(id) ON DELETE CASCADE,
            external_key text NOT NULL,
            name text NOT NULL,
            is_custom boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE(project_id, external_key),
            UNIQUE(project_id, name)
        );
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS clean_jira.field_values (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            issue_id uuid NOT NULL REFERENCES clean_jira.issues(id) ON DELETE CASCADE,
            field_key_id uuid NOT NULL REFERENCES clean_jira.field_keys(id) ON DELETE CASCADE,
            json_value jsonb,
            value text,
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE(issue_id, field_key_id)
        );
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS clean_jira.field_value_changelog (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            issue_id uuid NOT NULL REFERENCES clean_jira.issues(id) ON DELETE CASCADE,
            field_key_id uuid NOT NULL REFERENCES clean_jira.field_keys(id) ON DELETE CASCADE,
            old_value jsonb,
            new_value jsonb,
            changed_by_id uuid REFERENCES clean_jira.jira_users(id),
            changed_at timestamptz NOT NULL,
            UNIQUE(issue_id, field_key_id, changed_at)
        );
        """
    )

    # Create board tables
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS clean_jira.boards (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id uuid NOT NULL REFERENCES clean_jira.projects(id) ON DELETE CASCADE,
            external_id text NOT NULL,
            name text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE(project_id, external_id)
        );
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS clean_jira.board_columns (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            board_id uuid NOT NULL REFERENCES clean_jira.boards(id) ON DELETE CASCADE,
            name text NOT NULL,
            position int NOT NULL,
            UNIQUE(board_id, position),
            UNIQUE(board_id, name)
        );
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS clean_jira.board_column_statuses (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            board_column_id uuid NOT NULL REFERENCES clean_jira.board_columns(id) ON DELETE CASCADE,
            status_id uuid NOT NULL REFERENCES clean_jira.issue_statuses(id) ON DELETE CASCADE,
            UNIQUE(board_column_id, status_id)
        );
        """
    )

    # Create comment tables
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS clean_jira.comments (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id uuid NOT NULL REFERENCES clean_jira.projects(id) ON DELETE CASCADE,
            external_id text NOT NULL,
            body text NOT NULL,
            author_id uuid REFERENCES clean_jira.jira_users(id),
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            UNIQUE(project_id, external_id)
        );
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS clean_jira.comment_issues (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            comment_id uuid NOT NULL REFERENCES clean_jira.comments(id) ON DELETE CASCADE,
            issue_id uuid NOT NULL REFERENCES clean_jira.issues(id) ON DELETE CASCADE,
            UNIQUE(comment_id, issue_id)
        );
        """
    )

    # Create relation tables
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS clean_jira.relation_issue_types (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id uuid NOT NULL REFERENCES clean_jira.projects(id) ON DELETE CASCADE,
            external_id text NOT NULL,
            name text NOT NULL,
            UNIQUE(project_id, external_id)
        );
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS clean_jira.relation_issue_issues (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            relation_type_id uuid NOT NULL REFERENCES clean_jira.relation_issue_types(id) ON DELETE CASCADE,
            source_issue_id uuid NOT NULL REFERENCES clean_jira.issues(id) ON DELETE CASCADE,
            target_issue_id uuid NOT NULL REFERENCES clean_jira.issues(id) ON DELETE CASCADE,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE(relation_type_id, source_issue_id, target_issue_id)
        );
        """
    )

    # Create blocking tables
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS clean_jira.issue_comment_blockings (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            issue_id uuid NOT NULL REFERENCES clean_jira.issues(id) ON DELETE CASCADE,
            comment_id uuid NOT NULL REFERENCES clean_jira.comments(id) ON DELETE CASCADE,
            is_resolved boolean NOT NULL DEFAULT false,
            blocked_at timestamptz NOT NULL DEFAULT now(),
            resolved_at timestamptz,
            UNIQUE(issue_id, comment_id)
        );
        """
    )

    # Create indexes
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_projects_platform_project ON clean_jira.projects(platform_project_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_projects_external_key ON clean_jira.projects(platform_project_id, external_key);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_issue_types_project ON clean_jira.issue_types(project_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_issue_types_hierarchy ON clean_jira.issue_types(hierarchy_level);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_issue_statuses_project ON clean_jira.issue_statuses(project_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_issue_statuses_category ON clean_jira.issue_statuses(category);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_jira_users_project ON clean_jira.jira_users(project_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_jira_users_external ON clean_jira.jira_users(project_id, external_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_user_roles_user ON clean_jira.jira_user_issue_roles(user_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_user_roles_issue ON clean_jira.jira_user_issue_roles(issue_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_user_roles_type ON clean_jira.jira_user_issue_roles(role_type);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_issues_project ON clean_jira.issues(project_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_issues_type ON clean_jira.issues(type_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_issues_status ON clean_jira.issues(status_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_issues_parent ON clean_jira.issues(parent_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_issues_jira_created ON clean_jira.issues(jira_created_at);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_issues_jira_updated ON clean_jira.issues(jira_updated_at);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_issues_jira_resolved ON clean_jira.issues(jira_resolved_at) WHERE jira_resolved_at IS NOT NULL;"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_sprints_project ON clean_jira.sprints(project_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_sprints_status ON clean_jira.sprints(status);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_sprints_dates ON clean_jira.sprints(start_date, end_date);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_sprint_issues_sprint ON clean_jira.sprint_issues(sprint_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_sprint_issues_issue ON clean_jira.sprint_issues(issue_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_sprint_issues_active ON clean_jira.sprint_issues(is_active);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_sprint_issues_changelog_sprint ON clean_jira.sprint_issues_changelog(sprint_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_sprint_issues_changelog_issue ON clean_jira.sprint_issues_changelog(issue_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_sprint_issues_changelog_changed ON clean_jira.sprint_issues_changelog(changed_at);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_releases_project ON clean_jira.releases(project_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_releases_status ON clean_jira.releases(status);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_releases_dates ON clean_jira.releases(start_date, release_date);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_release_issues_release ON clean_jira.release_issues(release_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_release_issues_issue ON clean_jira.release_issues(issue_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_release_issues_active ON clean_jira.release_issues(is_active);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_field_keys_project ON clean_jira.field_keys(project_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_field_values_issue ON clean_jira.field_values(issue_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_field_values_field_key ON clean_jira.field_values(field_key_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_field_values_value ON clean_jira.field_values(value);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_field_value_changelog_issue ON clean_jira.field_value_changelog(issue_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_field_value_changelog_field_key ON clean_jira.field_value_changelog(field_key_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_field_value_changelog_changed ON clean_jira.field_value_changelog(changed_at);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_boards_project ON clean_jira.boards(project_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_board_columns_board ON clean_jira.board_columns(board_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_board_columns_position ON clean_jira.board_columns(board_id, position);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_comments_project ON clean_jira.comments(project_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_comments_author ON clean_jira.comments(author_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_comments_created ON clean_jira.comments(created_at);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_comment_issues_comment ON clean_jira.comment_issues(comment_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_comment_issues_issue ON clean_jira.comment_issues(issue_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_relation_issue_types_project ON clean_jira.relation_issue_types(project_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_relation_issue_issues_type ON clean_jira.relation_issue_issues(relation_type_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_relation_issue_issues_source ON clean_jira.relation_issue_issues(source_issue_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_relation_issue_issues_target ON clean_jira.relation_issue_issues(target_issue_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_issue_comment_blockings_issue ON clean_jira.issue_comment_blockings(issue_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_issue_comment_blockings_comment ON clean_jira.issue_comment_blockings(comment_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_issue_comment_blockings_resolved ON clean_jira.issue_comment_blockings(is_resolved);"
    )


def downgrade() -> None:
    """Drop clean_jira schema and all its contents."""
    op.execute("DROP SCHEMA IF EXISTS clean_jira CASCADE;")
