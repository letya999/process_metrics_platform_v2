"""Add issue status history table

Revision ID: 0007_add_issue_status_history
Revises: 0006_add_metrics_slice_tables
Create Date: 2025-12-14 22:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0007_add_issue_status_history"
down_revision = "0006_add_metrics_slice_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create issue_status_changelog table
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS clean_jira.issue_status_changelog (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            issue_id uuid NOT NULL REFERENCES clean_jira.issues(id) ON DELETE CASCADE,
            from_status_id uuid REFERENCES clean_jira.issue_statuses(id),
            to_status_id uuid NOT NULL REFERENCES clean_jira.issue_statuses(id),
            changed_by_id uuid REFERENCES clean_jira.jira_users(id),
            changed_at timestamptz NOT NULL,
            UNIQUE(issue_id, to_status_id, changed_at)
        );
        """
    )

    # Create indexes
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_isc_issue ON clean_jira.issue_status_changelog(issue_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_isc_changed ON clean_jira.issue_status_changelog(changed_at);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cj_isc_to_status ON clean_jira.issue_status_changelog(to_status_id);"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS clean_jira.issue_status_changelog CASCADE;")
