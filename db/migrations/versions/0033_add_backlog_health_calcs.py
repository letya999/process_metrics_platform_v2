"""add_backlog_health_calcs

Revision ID: 0033
Revises: 0032
Create Date: 2026-05-29

Register missing backlog health calc_codes that were present in the asset
but not seeded: backlog_avg_age_days, backlog_stale_pct, backlog_stale_count,
backlog_oldest_days.
"""

from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        WITH defs AS (SELECT id, metric_code FROM metrics.definitions),
             grns AS (SELECT id, grain_code FROM metrics.grains)
        INSERT INTO metrics.calculations (definition_id, calc_code, grain_id, unit_code, uses_commitment_points)
        VALUES
        ((SELECT id FROM defs WHERE metric_code = 'backlog_growth'), 'backlog_avg_age_days',  (SELECT id FROM grns WHERE grain_code = 'day'), 'days',    false),
        ((SELECT id FROM defs WHERE metric_code = 'backlog_growth'), 'backlog_stale_pct',     (SELECT id FROM grns WHERE grain_code = 'day'), 'percent', false),
        ((SELECT id FROM defs WHERE metric_code = 'backlog_growth'), 'backlog_stale_count',   (SELECT id FROM grns WHERE grain_code = 'day'), 'issues',  false),
        ((SELECT id FROM defs WHERE metric_code = 'backlog_growth'), 'backlog_oldest_days',   (SELECT id FROM grns WHERE grain_code = 'day'), 'days',    false)
        ON CONFLICT (calc_code) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM metrics.calculations
        WHERE calc_code IN (
            'backlog_avg_age_days',
            'backlog_stale_pct',
            'backlog_stale_count',
            'backlog_oldest_days'
        );
        """
    )
