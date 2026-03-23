"""add_phase1_clean_jira_tables

Revision ID: 0029
Revises: 0028
Create Date: 2026-03-24

"""

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade():
    # labels
    op.execute(
        text(
            """
        CREATE TABLE IF NOT EXISTS clean_jira.labels (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id uuid NOT NULL REFERENCES clean_jira.projects(id) ON DELETE CASCADE,
            name text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE(project_id, name)
        );
    """
        )
    )

    op.execute(
        text(
            """
        CREATE TABLE IF NOT EXISTS clean_jira.issue_labels (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            issue_id uuid NOT NULL REFERENCES clean_jira.issues(id) ON DELETE CASCADE,
            label_id uuid NOT NULL REFERENCES clean_jira.labels(id) ON DELETE CASCADE,
            UNIQUE(issue_id, label_id)
        );
    """
        )
    )

    op.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_cj_labels_project ON clean_jira.labels(project_id);"
        )
    )
    op.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_cj_issue_labels_issue ON clean_jira.issue_labels(issue_id);"
        )
    )
    op.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_cj_issue_labels_label ON clean_jira.issue_labels(label_id);"
        )
    )

    # worklogs
    op.execute(
        text(
            """
        CREATE TABLE IF NOT EXISTS clean_jira.worklogs (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            issue_id uuid NOT NULL REFERENCES clean_jira.issues(id) ON DELETE CASCADE,
            external_id text NOT NULL,
            author_id uuid REFERENCES clean_jira.jira_users(id),
            time_spent_seconds int NOT NULL,
            started_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE(issue_id, external_id)
        );
    """
        )
    )

    op.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_cj_worklogs_issue ON clean_jira.worklogs(issue_id);"
        )
    )
    op.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_cj_worklogs_author ON clean_jira.worklogs(author_id);"
        )
    )
    op.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_cj_worklogs_started ON clean_jira.worklogs(started_at);"
        )
    )

    # priorities
    op.execute(
        text(
            """
        CREATE TABLE IF NOT EXISTS clean_jira.issue_priorities (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id uuid NOT NULL REFERENCES clean_jira.projects(id) ON DELETE CASCADE,
            external_id text NOT NULL,
            name text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE(project_id, external_id),
            UNIQUE(project_id, name)
        );
    """
        )
    )

    op.execute(
        text(
            "ALTER TABLE clean_jira.issues ADD COLUMN IF NOT EXISTS priority_id uuid REFERENCES clean_jira.issue_priorities(id);"
        )
    )
    op.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_cj_issue_priorities_project ON clean_jira.issue_priorities(project_id);"
        )
    )
    op.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_cj_issues_priority ON clean_jira.issues(priority_id);"
        )
    )

    # resolutions
    op.execute(
        text(
            """
        CREATE TABLE IF NOT EXISTS clean_jira.issue_resolutions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id uuid NOT NULL REFERENCES clean_jira.projects(id) ON DELETE CASCADE,
            external_id text NOT NULL,
            name text NOT NULL,
            description text,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE(project_id, external_id),
            UNIQUE(project_id, name)
        );
    """
        )
    )

    op.execute(
        text(
            "ALTER TABLE clean_jira.issues ADD COLUMN IF NOT EXISTS resolution_id uuid REFERENCES clean_jira.issue_resolutions(id);"
        )
    )
    op.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_cj_issue_resolutions_project ON clean_jira.issue_resolutions(project_id);"
        )
    )
    op.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_cj_issues_resolution ON clean_jira.issues(resolution_id);"
        )
    )


def downgrade():
    op.execute(
        text("ALTER TABLE clean_jira.issues DROP COLUMN IF EXISTS resolution_id;")
    )
    op.execute(text("DROP TABLE IF EXISTS clean_jira.issue_resolutions;"))
    op.execute(text("ALTER TABLE clean_jira.issues DROP COLUMN IF EXISTS priority_id;"))
    op.execute(text("DROP TABLE IF EXISTS clean_jira.issue_priorities;"))
    op.execute(text("DROP TABLE IF EXISTS clean_jira.worklogs;"))
    op.execute(text("DROP TABLE IF EXISTS clean_jira.issue_labels;"))
    op.execute(text("DROP TABLE IF EXISTS clean_jira.labels;"))
