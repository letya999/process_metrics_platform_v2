"""Update pipeline_runs comments and seed jira_sync pipeline

Revision ID: 0003_update_pipeline_runs_jira_metadata
Revises: 0002_add_integration_sync_checkpoints
Create Date: 2025-10-20
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0003_pipeline_runs_jira"
down_revision = "0002_sync_checkpoints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add/refresh comments describing expected JSONB structures for Jira
    # (split for asyncpg)
    op.execute(
        "COMMENT ON COLUMN platform.pipeline_runs.config IS "
        "'JSONB config for a run; for jira_sync contains keys like "
        "project_uuids (list of UUID strings), date_from/date_to (ISO8601), "
        "dataset_name (string)'"
    )
    op.execute(
        "COMMENT ON COLUMN platform.pipeline_runs.metrics IS "
        "'JSONB metrics for a run; for jira_sync contains counts per resource "
        "(issues, sprints, changelog, comments), load_info from DLT "
        "(rows_written, elapsed)'"
    )

    # Seed pipelines registry with jira_sync if missing
    op.execute(
        """
        INSERT INTO platform.pipelines (name, description, is_active, config)
        VALUES (
          'jira_sync',
          'Jira Cloud data synchronization pipeline (Prefect + DLT)',
          true,
          '{"default_dataset": "raw_jira_cloud_dlt"}'::jsonb
        )
        ON CONFLICT (name) DO NOTHING;
        """
    )


def downgrade() -> None:
    # Revert comments to a generic description (optional)
    op.execute(
        """
        COMMENT ON COLUMN platform.pipeline_runs.config IS
        'Custom pipeline configuration in JSON format';
        COMMENT ON COLUMN platform.pipeline_runs.metrics IS
        'Execution metrics in JSON format';
        """
    )
    # Do not remove seeded pipeline row to avoid data loss
