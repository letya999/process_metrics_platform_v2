"""add_external_id_indexes

Revision ID: 0031
Revises: 0030
Create Date: 2026-03-24

"""

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_cj_issues_ext_id ON clean_jira.issues(external_id);"
        )
    )
    op.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_cj_sprints_ext_id ON clean_jira.sprints(external_id);"
        )
    )
    op.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_cj_releases_ext_id ON clean_jira.releases(external_id);"
        )
    )
    op.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_cj_jira_users_ext_id ON clean_jira.jira_users(external_id);"
        )
    )
    op.execute(
        text(
            """
        CREATE INDEX IF NOT EXISTS idx_cj_sprint_changelog_sprint_id_field
            ON clean_jira.sprint_changelog(sprint_id, field_name, changed_at DESC);
    """
        )
    )


def downgrade():
    op.execute(text("DROP INDEX IF EXISTS clean_jira.idx_cj_issues_ext_id;"))
    op.execute(text("DROP INDEX IF EXISTS clean_jira.idx_cj_sprints_ext_id;"))
    op.execute(text("DROP INDEX IF EXISTS clean_jira.idx_cj_releases_ext_id;"))
    op.execute(text("DROP INDEX IF EXISTS clean_jira.idx_cj_jira_users_ext_id;"))
    op.execute(
        text("DROP INDEX IF EXISTS clean_jira.idx_cj_sprint_changelog_sprint_id_field;")
    )
