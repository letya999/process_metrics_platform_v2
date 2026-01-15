"""create_metrics_mvs

Revision ID: 0009_create_metrics_mvs
Revises: 0008_fix_schema_inconsistencies
Create Date: 2025-12-16 00:00:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "0009_create_metrics_mvs"
down_revision = "0008_fix_schema_inconsistencies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Applying db/views/metrics.sql content
    # Created 3 MV definitions on top of the fact tables created in 0008

    # 1. metrics.mv_lead_time
    op.execute(
        """
    CREATE MATERIALIZED VIEW IF NOT EXISTS metrics.mv_lead_time AS
    SELECT
        i.id AS issue_id,
        i.external_key AS issue_key,
        i.summary,
        f.project_id,
        p.external_key AS project_key,
        p.name AS project_name,
        it.name AS issue_type,
        it.hierarchy_level,
        ist.name AS status_name,
        ist.category AS status_category,
        f.commitment_start_at,
        f.commitment_end_at,
        f.lead_time_days,
         -- Lead time in hours
        (f.lead_time_days * 24) AS lead_time_hours,
        i.db_updated_at
    FROM metrics.fact_lead_time f
    JOIN clean_jira.issues i ON i.id = f.issue_id
    JOIN clean_jira.projects p ON f.project_id = p.id
    JOIN clean_jira.issue_types it ON i.type_id = it.id
    JOIN clean_jira.issue_statuses ist ON i.status_id = ist.id
    WITH DATA;

    CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_lead_time_issue_id
        ON metrics.mv_lead_time(issue_id);
    CREATE INDEX IF NOT EXISTS idx_mv_lead_time_project
        ON metrics.mv_lead_time(project_id, commitment_end_at);
    CREATE INDEX IF NOT EXISTS idx_mv_lead_time_type
        ON metrics.mv_lead_time(issue_type);

    COMMENT ON MATERIALIZED VIEW metrics.mv_lead_time IS
        'Lead time per resolved issue (reading from fact_lead_time which uses board logic)';
    """
    )

    # 2. metrics.mv_velocity
    op.execute(
        """
    CREATE MATERIALIZED VIEW IF NOT EXISTS metrics.mv_velocity AS
    SELECT
        f.iteration_id AS sprint_id,
        f.iteration_name AS sprint_name,
        f.project_id,
        p.external_key AS project_key,
        p.name AS project_name,
        f.start_date,
        f.end_date,
        f.planned_story_points,
        f.completed_story_points,
        f.planned_issues,
        f.completed_issues,
        -- Completion rate (Points)
        CASE
            WHEN f.planned_story_points > 0 THEN
                ROUND((f.completed_story_points::numeric / f.planned_story_points::numeric) * 100, 2)
            ELSE 0
        END AS completion_rate_points_pct,
         -- Completion rate (Issues)
        CASE
            WHEN f.planned_issues > 0 THEN
                ROUND((f.completed_issues::numeric / f.planned_issues::numeric) * 100, 2)
            ELSE 0
        END AS completion_rate_issues_pct
    FROM metrics.fact_velocity f
    JOIN clean_jira.projects p ON f.project_id = p.id
    WHERE f.issue_type IS NULL
      AND f.custom_field_value IS NULL -- aggregates only
    WITH DATA;

    CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_velocity_sprint_id
        ON metrics.mv_velocity(sprint_id);
    CREATE INDEX IF NOT EXISTS idx_mv_velocity_project
        ON metrics.mv_velocity(project_id, start_date);

    COMMENT ON MATERIALIZED VIEW metrics.mv_velocity IS
        'Velocity metrics per sprint (reading from fact_velocity calculated by job)';
    """
    )

    # 3. metrics.mv_throughput
    op.execute(
        """
    CREATE MATERIALIZED VIEW IF NOT EXISTS metrics.mv_throughput AS
    SELECT
        DATE(f.commitment_end_at) AS resolved_date,
        f.project_id,
        p.external_key AS project_key,
        p.name AS project_name,
        it.name AS issue_type,
        it.hierarchy_level,
        count(*) AS issues_completed,
        ROUND(AVG(f.lead_time_days)::numeric, 2) AS avg_lead_time_days
    FROM metrics.fact_lead_time f
    JOIN clean_jira.projects p ON f.project_id = p.id
    JOIN clean_jira.issues i ON i.id = f.issue_id
    JOIN clean_jira.issue_types it ON i.type_id = it.id
    WHERE f.commitment_end_at IS NOT NULL
    GROUP BY DATE(f.commitment_end_at), f.project_id, p.external_key, p.name, it.name, it.hierarchy_level
    WITH DATA;

    CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_throughput_date_project_type
        ON metrics.mv_throughput(resolved_date, project_id, issue_type);
    CREATE INDEX IF NOT EXISTS idx_mv_throughput_project
        ON metrics.mv_throughput(project_id, resolved_date);

    COMMENT ON MATERIALIZED VIEW metrics.mv_throughput IS
        'Daily throughput (issues completed per day by type, from fact_lead_time)';
    """
    )

    # 4. metrics.mv_velocity_slice
    op.execute(
        """
    CREATE MATERIALIZED VIEW IF NOT EXISTS metrics.mv_velocity_slice AS
    SELECT
        f.iteration_id AS sprint_id,
        f.iteration_name AS sprint_name,
        f.project_id,
        p.external_key AS project_key,
        p.name AS project_name,
        f.start_date,
        f.end_date,
        f.slice_dim,
        f.slice_value,
        f.planned_story_points,
        f.completed_story_points,
        f.planned_issues,
        f.completed_issues,
        -- Completion rate (Points)
        CASE
            WHEN f.planned_story_points > 0 THEN
                ROUND((f.completed_story_points::numeric / f.planned_story_points::numeric) * 100, 2)
            ELSE 0
        END AS completion_rate_points_pct,
         -- Completion rate (Issues)
        CASE
            WHEN f.planned_issues > 0 THEN
                ROUND((f.completed_issues::numeric / f.planned_issues::numeric) * 100, 2)
            ELSE 0
        END AS completion_rate_issues_pct
    FROM metrics.fact_velocity_slice f
    JOIN clean_jira.projects p ON f.project_id = p.id
    WITH DATA;

    CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_velocity_slice_sprint_dim_val
        ON metrics.mv_velocity_slice(sprint_id, slice_dim, slice_value);
    CREATE INDEX IF NOT EXISTS idx_mv_velocity_slice_project
        ON metrics.mv_velocity_slice(project_id, start_date);

    COMMENT ON MATERIALIZED VIEW metrics.mv_velocity_slice IS
        'Velocity metrics per sprint sliced by type/field (Plan vs Fact)';
    """
    )

    # 5. metrics.mv_lead_time_slice
    op.execute(
        """
    CREATE MATERIALIZED VIEW IF NOT EXISTS metrics.mv_lead_time_slice AS
    SELECT
        i.id AS issue_id,
        i.external_key AS issue_key,
        i.summary,
        f.project_id,
        p.external_key AS project_key,
        p.name AS project_name,
        it.name AS issue_type,
        f.slice_dim,
        f.slice_value,
        f.commitment_start_at,
        f.commitment_end_at,
        f.lead_time_days,
         -- Lead time in hours
        (f.lead_time_days * 24) AS lead_time_hours,
        i.db_updated_at
    FROM metrics.fact_lead_time_slice f
    JOIN clean_jira.issues i ON i.id = f.issue_id
    JOIN clean_jira.projects p ON f.project_id = p.id
    JOIN clean_jira.issue_types it ON i.type_id = it.id
    WITH DATA;

    CREATE INDEX IF NOT EXISTS idx_mv_lead_time_slice_project_dim
        ON metrics.mv_lead_time_slice(project_id, slice_dim, slice_value);
    CREATE INDEX IF NOT EXISTS idx_mv_lead_time_slice_end_date
        ON metrics.mv_lead_time_slice(commitment_end_at);

    COMMENT ON MATERIALIZED VIEW metrics.mv_lead_time_slice IS
        'Lead time per issue sliced by configured dimensions';
    """
    )

    # 6. metrics.mv_lead_time_bins_slice
    op.execute(
        """
    CREATE MATERIALIZED VIEW IF NOT EXISTS metrics.mv_lead_time_bins_slice AS
    SELECT
        f.project_id,
        p.external_key AS project_key,
        p.name AS project_name,
        f.slice_dim,
        f.slice_value,
        f.bin_number,
        f.tickets_count
    FROM metrics.fact_lead_time_bins_slice f
    JOIN clean_jira.projects p ON f.project_id = p.id
    WITH DATA;

    CREATE INDEX IF NOT EXISTS idx_mv_lt_bins_slice_project_dim
        ON metrics.mv_lead_time_bins_slice(project_id, slice_dim, slice_value);

    COMMENT ON MATERIALIZED VIEW metrics.mv_lead_time_bins_slice IS
        'Lead time histogram bins sliced by configured dimensions';
    """
    )

    # 7. Refresh function
    op.execute(
        """
    CREATE OR REPLACE FUNCTION metrics.refresh_all_views()
    RETURNS void AS $$
    BEGIN
        REFRESH MATERIALIZED VIEW CONCURRENTLY metrics.mv_lead_time;
        REFRESH MATERIALIZED VIEW CONCURRENTLY metrics.mv_velocity;
        REFRESH MATERIALIZED VIEW CONCURRENTLY metrics.mv_throughput;

        -- Refresh sliced views (check existence just in case, though they are created above)
        REFRESH MATERIALIZED VIEW CONCURRENTLY metrics.mv_velocity_slice;
        REFRESH MATERIALIZED VIEW CONCURRENTLY metrics.mv_lead_time_slice;
        REFRESH MATERIALIZED VIEW CONCURRENTLY metrics.mv_lead_time_bins_slice;
    END;
    $$ LANGUAGE plpgsql;

    COMMENT ON FUNCTION metrics.refresh_all_views() IS
        'Refresh all metrics materialized views including sliced views';
    """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP FUNCTION IF EXISTS metrics.refresh_all_views();
        DROP MATERIALIZED VIEW IF EXISTS metrics.mv_lead_time_bins_slice CASCADE;
        DROP MATERIALIZED VIEW IF EXISTS metrics.mv_lead_time_slice CASCADE;
        DROP MATERIALIZED VIEW IF EXISTS metrics.mv_velocity_slice CASCADE;
        DROP MATERIALIZED VIEW IF EXISTS metrics.mv_throughput CASCADE;
        DROP MATERIALIZED VIEW IF EXISTS metrics.mv_velocity CASCADE;
        DROP MATERIALIZED VIEW IF EXISTS metrics.mv_lead_time CASCADE;
    """
    )
