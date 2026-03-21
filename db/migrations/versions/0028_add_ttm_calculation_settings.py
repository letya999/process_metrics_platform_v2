"""add_ttm_calculation_settings

Revision ID: 0028
Revises: 0027
Create Date: 2026-03-22

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade():
    # Insert global record for ttm_days with Epic filter
    op.execute(
        """
        INSERT INTO metrics.calculation_settings (
            target_calculation_id,
            settings_type,
            settings_json,
            project_id,
            enabled
        )
        VALUES (
            (SELECT id FROM metrics.calculations WHERE calc_code = 'ttm_days'),
            'issue_type_filter',
            '{"include": ["Epic"]}',
            NULL,
            true
        )
    """
    )


def downgrade():
    op.execute(
        """
        DELETE FROM metrics.calculation_settings
        WHERE target_calculation_id = (SELECT id FROM metrics.calculations WHERE calc_code = 'ttm_days')
        AND settings_type = 'issue_type_filter'
    """
    )
