"""seed_metric_metadata

Revision ID: 0020
Revises: 0019
Create Date: 2026-03-19 12:00:00.000000

"""

import datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0020_seed_metadata"
down_revision = "0019_add_fact_values"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Seed grains
    op.execute(
        """
        INSERT INTO metrics.grains (grain_code, description) VALUES
        ('issue', 'One row per Jira issue'),
        ('sprint', 'One row per sprint'),
        ('week', 'One row per ISO week'),
        ('day', 'One row per calendar day'),
        ('release', 'One row per Jira release')
        ON CONFLICT (grain_code) DO NOTHING;
        """
    )

    # 2. Seed definitions
    op.execute(
        """
        INSERT INTO metrics.definitions (metric_code) VALUES
        ('velocity'), ('lead_time'), ('throughput'), ('cfd'),
        ('backlog_growth'), ('ttm'), ('aging'), ('flow_efficiency')
        ON CONFLICT (metric_code) DO NOTHING;
        """
    )

    # 3. Seed calculations
    op.execute(
        """
        WITH defs AS (SELECT id, metric_code FROM metrics.definitions),
             grns AS (SELECT id, grain_code FROM metrics.grains)
        INSERT INTO metrics.calculations (definition_id, calc_code, grain_id, unit_code, uses_commitment_points)
        VALUES
        ((SELECT id FROM defs WHERE metric_code = 'velocity'), 'velocity_planned_sp', (SELECT id FROM grns WHERE grain_code = 'sprint'), 'story_points', false),
        ((SELECT id FROM defs WHERE metric_code = 'velocity'), 'velocity_completed_sp', (SELECT id FROM grns WHERE grain_code = 'sprint'), 'story_points', false),
        ((SELECT id FROM defs WHERE metric_code = 'velocity'), 'velocity_planned_count', (SELECT id FROM grns WHERE grain_code = 'sprint'), 'issues', false),
        ((SELECT id FROM defs WHERE metric_code = 'velocity'), 'velocity_completed_count', (SELECT id FROM grns WHERE grain_code = 'sprint'), 'issues', false),

        ((SELECT id FROM defs WHERE metric_code = 'lead_time'), 'lead_time_days', (SELECT id FROM grns WHERE grain_code = 'issue'), 'days', true),

        ((SELECT id FROM defs WHERE metric_code = 'throughput'), 'throughput_count', (SELECT id FROM grns WHERE grain_code = 'week'), 'issues', false),

        ((SELECT id FROM defs WHERE metric_code = 'cfd'), 'cfd_count', (SELECT id FROM grns WHERE grain_code = 'day'), 'issues', false),

        ((SELECT id FROM defs WHERE metric_code = 'backlog_growth'), 'backlog_size', (SELECT id FROM grns WHERE grain_code = 'day'), 'issues', false),
        ((SELECT id FROM defs WHERE metric_code = 'backlog_growth'), 'backlog_created', (SELECT id FROM grns WHERE grain_code = 'day'), 'issues', false),
        ((SELECT id FROM defs WHERE metric_code = 'backlog_growth'), 'backlog_resolved', (SELECT id FROM grns WHERE grain_code = 'day'), 'issues', false),
        ((SELECT id FROM defs WHERE metric_code = 'backlog_growth'), 'backlog_net_growth', (SELECT id FROM grns WHERE grain_code = 'day'), 'issues', false),

        ((SELECT id FROM defs WHERE metric_code = 'ttm'), 'ttm_days', (SELECT id FROM grns WHERE grain_code = 'issue'), 'days', true),

        ((SELECT id FROM defs WHERE metric_code = 'aging'), 'aging_days', (SELECT id FROM grns WHERE grain_code = 'issue'), 'days', true),

        ((SELECT id FROM defs WHERE metric_code = 'flow_efficiency'), 'flow_active_days', (SELECT id FROM grns WHERE grain_code = 'issue'), 'days', true),
        ((SELECT id FROM defs WHERE metric_code = 'flow_efficiency'), 'flow_wait_days', (SELECT id FROM grns WHERE grain_code = 'issue'), 'days', true),
        ((SELECT id FROM defs WHERE metric_code = 'flow_efficiency'), 'flow_efficiency_pct', (SELECT id FROM grns WHERE grain_code = 'issue'), 'percent', true)
        ON CONFLICT (calc_code) DO NOTHING;
        """
    )

    # 4. Seed units
    op.execute(
        """
        INSERT INTO metrics.units (project_id, unit_code, display_symbol) VALUES
        (NULL, 'story_points', 'SP'),
        (NULL, 'issues', 'items'),
        (NULL, 'days', 'd'),
        (NULL, 'hours', 'h'),
        (NULL, 'percent', '%')
        ON CONFLICT DO NOTHING;
        """
    )

    # 5. Seed dim_dates (2020-2030)
    start_date = datetime.date(2020, 1, 1)
    end_date = datetime.date(2030, 12, 31)
    delta = datetime.timedelta(days=1)

    dim_dates_table = sa.table(
        "dim_dates",
        sa.column("time_id", sa.Integer),
        sa.column("full_date", sa.Date),
        sa.column("week_num", sa.Integer),
        sa.column("month_num", sa.Integer),
        sa.column("quarter", sa.Integer),
        sa.column("year", sa.Integer),
        schema="metrics",
    )

    curr_date = start_date
    batch = []
    while curr_date <= end_date:
        time_id = int(curr_date.strftime("%Y%m%d"))
        # ISO week
        iso_year, iso_week, iso_weekday = curr_date.isocalendar()
        month_num = curr_date.month
        quarter = (month_num - 1) // 3 + 1
        year = curr_date.year

        batch.append(
            {
                "time_id": time_id,
                "full_date": curr_date,
                "week_num": iso_week,
                "month_num": month_num,
                "quarter": quarter,
                "year": year,
            }
        )
        curr_date += delta

        if len(batch) >= 1000:
            op.bulk_insert(dim_dates_table, batch)
            batch = []

    if batch:
        op.bulk_insert(dim_dates_table, batch)


def downgrade() -> None:
    op.execute("TRUNCATE metrics.dim_dates CASCADE")
    op.execute("DELETE FROM metrics.units WHERE project_id IS NULL")
    op.execute("DELETE FROM metrics.calculations CASCADE")
    op.execute("DELETE FROM metrics.definitions CASCADE")
    op.execute("DELETE FROM metrics.grains CASCADE")
