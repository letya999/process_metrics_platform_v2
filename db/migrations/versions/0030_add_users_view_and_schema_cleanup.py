"""add_users_view_and_schema_cleanup

Revision ID: 0030
Revises: 0029
Create Date: 2026-03-24

"""

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade():
    # v_unique_users view
    op.execute(
        text(
            """
        CREATE OR REPLACE VIEW clean_jira.v_unique_users AS
        SELECT DISTINCT ON (external_id)
            id, project_id, external_id, display_name, created_at, updated_at
        FROM clean_jira.jira_users
        ORDER BY external_id, updated_at DESC;
    """
        )
    )

    # drop raw_jira_staging schema (no longer needed)
    op.execute(text("DROP SCHEMA IF EXISTS raw_jira_staging CASCADE;"))

    # fix field_keys unique constraint (allow same name, different key)
    op.execute(
        text(
            """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'field_keys_project_id_name_key'
                  AND conrelid = 'clean_jira.field_keys'::regclass
            ) THEN
                ALTER TABLE clean_jira.field_keys DROP CONSTRAINT field_keys_project_id_name_key;
            END IF;
        END $$;
    """
        )
    )
    op.execute(text("DROP INDEX IF EXISTS clean_jira.field_keys_project_id_name_key;"))


def downgrade():
    op.execute(text("DROP VIEW IF EXISTS clean_jira.v_unique_users;"))
    # raw_jira_staging and field_keys constraint cannot be reliably reversed
