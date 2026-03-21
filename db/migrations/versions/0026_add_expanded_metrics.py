"""Add expanded metrics (22 new calculations)

Revision ID: 0026
Revises: 0025
Create Date: 2026-03-21 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade():
    # Verify required definitions exist
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT COUNT(*) FROM metrics.definitions WHERE metric_code IN ('throughput', 'aging', 'ttm', 'velocity', 'lead_time', 'cfd', 'backlog_growth', 'flow_efficiency')"
        )
    ).scalar()
    if result != 8:
        raise Exception(
            f"Expected 8 existing definitions, found {result}. Run prior migrations first."
        )

    # 1.1 New grain: project
    op.execute(
        "INSERT INTO metrics.grains (grain_code, description) VALUES ('project', 'One row per project (release/version scope)') ON CONFLICT (grain_code) DO NOTHING;"
    )

    # 1.2 New unit: ratio
    op.execute(
        "INSERT INTO metrics.units (project_id, unit_code, display_symbol) VALUES (NULL, 'ratio', 'x') ON CONFLICT DO NOTHING;"
    )

    # 1.3 New definitions (7)
    op.execute(
        "INSERT INTO metrics.definitions (metric_code) VALUES ('sprint_health'), ('flow_dynamics'), ('quality'), ('delivery'), ('waste'), ('estimation'), ('cycle_time') ON CONFLICT (metric_code) DO NOTHING;"
    )

    # 1.4 New calculations (22 total)
    op.execute(
        """
        WITH defs AS (SELECT id, metric_code FROM metrics.definitions),
             grns AS (SELECT id, grain_code FROM metrics.grains)
        INSERT INTO metrics.calculations (definition_id, calc_code, grain_id, unit_code, uses_commitment_points)
        VALUES
          ((SELECT id FROM defs WHERE metric_code = 'sprint_health'), 'sprint_added_issues_count', (SELECT id FROM grns WHERE grain_code = 'sprint'), 'issues', false),
          ((SELECT id FROM defs WHERE metric_code = 'sprint_health'), 'sprint_added_sp_sum', (SELECT id FROM grns WHERE grain_code = 'sprint'), 'story_points', false),
          ((SELECT id FROM defs WHERE metric_code = 'sprint_health'), 'sprint_removed_issues_count', (SELECT id FROM grns WHERE grain_code = 'sprint'), 'issues', false),
          ((SELECT id FROM defs WHERE metric_code = 'sprint_health'), 'sprint_removed_sp_sum', (SELECT id FROM grns WHERE grain_code = 'sprint'), 'story_points', false),
          ((SELECT id FROM defs WHERE metric_code = 'sprint_health'), 'sprint_spillover_count', (SELECT id FROM grns WHERE grain_code = 'sprint'), 'issues', false),
          ((SELECT id FROM defs WHERE metric_code = 'sprint_health'), 'sprint_burndown_remaining_sp', (SELECT id FROM grns WHERE grain_code = 'day'), 'story_points', false),
          ((SELECT id FROM defs WHERE metric_code = 'sprint_health'), 'activation_velocity_pct', (SELECT id FROM grns WHERE grain_code = 'day'), 'percent', true),
          ((SELECT id FROM defs WHERE metric_code = 'sprint_health'), 'field_value_sprint_pct', (SELECT id FROM grns WHERE grain_code = 'sprint'), 'percent', false),
          ((SELECT id FROM defs WHERE metric_code = 'sprint_health'), 'unestimated_closed_count', (SELECT id FROM grns WHERE grain_code = 'sprint'), 'issues', true),
          ((SELECT id FROM defs WHERE metric_code = 'flow_dynamics'), 'daily_status_entry_count', (SELECT id FROM grns WHERE grain_code = 'day'), 'issues', false),
          ((SELECT id FROM defs WHERE metric_code = 'flow_dynamics'), 'field_change_count', (SELECT id FROM grns WHERE grain_code = 'sprint'), 'issues', false),
          ((SELECT id FROM defs WHERE metric_code = 'throughput'), 'input_flow_weekly', (SELECT id FROM grns WHERE grain_code = 'week'), 'issues', true),
          ((SELECT id FROM defs WHERE metric_code = 'quality'), 'defect_density_by_type', (SELECT id FROM grns WHERE grain_code = 'sprint'), 'ratio', false),
          ((SELECT id FROM defs WHERE metric_code = 'quality'), 'backflow_column_rate', (SELECT id FROM grns WHERE grain_code = 'sprint'), 'percent', true),
          ((SELECT id FROM defs WHERE metric_code = 'delivery'), 'release_burnup_scope_sp', (SELECT id FROM grns WHERE grain_code = 'project'), 'story_points', false),
          ((SELECT id FROM defs WHERE metric_code = 'delivery'), 'release_burnup_done_sp', (SELECT id FROM grns WHERE grain_code = 'project'), 'story_points', true),
          ((SELECT id FROM defs WHERE metric_code = 'cycle_time'), 'issue_lifetime_days', (SELECT id FROM grns WHERE grain_code = 'issue'), 'days', false),
          ((SELECT id FROM defs WHERE metric_code = 'cycle_time'), 'cycle_time_custom', (SELECT id FROM grns WHERE grain_code = 'issue'), 'days', true),
          ((SELECT id FROM defs WHERE metric_code = 'waste'), 'cancellation_rate_weekly', (SELECT id FROM grns WHERE grain_code = 'week'), 'issues', false),
          ((SELECT id FROM defs WHERE metric_code = 'estimation'), 'estimate_volatility_abs', (SELECT id FROM grns WHERE grain_code = 'issue'), 'story_points', false),
          ((SELECT id FROM defs WHERE metric_code = 'aging'), 'blocked_time_total', (SELECT id FROM grns WHERE grain_code = 'issue'), 'hours', false),
          ((SELECT id FROM defs WHERE metric_code = 'aging'), 'stale_days', (SELECT id FROM grns WHERE grain_code = 'issue'), 'days', false),
          ((SELECT id FROM defs WHERE metric_code = 'ttm'), 'epic_delivery_time', (SELECT id FROM grns WHERE grain_code = 'issue'), 'days', true)
        ON CONFLICT (calc_code) DO NOTHING;
        """
    )


def downgrade():
    op.execute(
        """
        DELETE FROM metrics.calculations WHERE calc_code IN (
            'sprint_added_issues_count', 'sprint_added_sp_sum', 'sprint_removed_issues_count',
            'sprint_removed_sp_sum', 'sprint_spillover_count', 'sprint_burndown_remaining_sp',
            'activation_velocity_pct', 'field_value_sprint_pct', 'unestimated_closed_count',
            'daily_status_entry_count', 'field_change_count', 'input_flow_weekly',
            'defect_density_by_type', 'backflow_column_rate', 'release_burnup_scope_sp',
            'release_burnup_done_sp', 'issue_lifetime_days', 'cycle_time_custom',
            'cancellation_rate_weekly', 'estimate_volatility_abs', 'blocked_time_total',
            'stale_days', 'epic_delivery_time'
        )
    """
    )
    op.execute(
        "DELETE FROM metrics.definitions WHERE metric_code IN ('sprint_health','flow_dynamics','quality','delivery','waste','estimation','cycle_time')"
    )
    op.execute("DELETE FROM metrics.grains WHERE grain_code = 'project'")
    op.execute(
        "DELETE FROM metrics.units WHERE unit_code = 'ratio' AND project_id IS NULL"
    )
