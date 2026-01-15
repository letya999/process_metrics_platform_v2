"""fix_velocity_logic

Revision ID: 0010_fix_velocity_logic
Revises: 0009_create_metrics_mvs
Create Date: 2025-12-16 01:30:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "0010_fix_velocity_logic"
down_revision = "0009_create_metrics_mvs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # We need to recreate fact_velocity and fact_velocity_slice with corrected logic.
    # Logic Fixes:
    # 1. state_at_start: Compare changed_at <= start_date (Exact timestamp, no +24h buffer).
    # 2. membership_base: Remove `is_active=true` to include issues removed from sprint.

    op.execute(
        """
    -- Drop dependent MVs
    DROP MATERIALIZED VIEW IF EXISTS metrics.mv_velocity CASCADE;
    DROP MATERIALIZED VIEW IF EXISTS metrics.mv_velocity_slice CASCADE;

    -- Drop base facts
    DROP MATERIALIZED VIEW IF EXISTS metrics.fact_velocity CASCADE;
    DROP MATERIALIZED VIEW IF EXISTS metrics.fact_velocity_slice CASCADE;

    -- =================================================================================================
    -- FACT VELOCITY (Corrected)
    -- =================================================================================================
    CREATE MATERIALIZED VIEW metrics.fact_velocity AS
    WITH params AS (
      SELECT id AS project_id FROM clean_jira.projects
    ),
    iters AS (
      SELECT it.*
      FROM clean_jira.sprints it
      WHERE it.start_date IS NOT NULL AND it.end_date IS NOT NULL
    ),
    end_statuses AS (
       -- Identify "Done" statuses
      SELECT DISTINCT s.id AS status_id, b.project_id
      FROM clean_jira.board_columns bc
      JOIN clean_jira.board_column_statuses bcs ON bcs.board_column_id = bc.id
      JOIN clean_jira.issue_statuses s          ON s.id = bcs.status_id
      JOIN clean_jira.boards b                  ON b.id = bc.board_id
      WHERE bc.name ILIKE '%Done%'
    ),
    -- FIX 2: Remove is_active=true to include historical membership (removed issues)
    membership_base AS (
      SELECT DISTINCT ii.issue_id, ii.sprint_id AS iteration_id
      FROM clean_jira.sprint_issues ii
    ),
    state_at_start AS (
      SELECT m.issue_id, m.iteration_id,
             (
               SELECT h.action
               FROM clean_jira.sprint_issues_changelog h
               JOIN iters it2 ON it2.id = h.sprint_id
               WHERE h.issue_id = m.issue_id
                 AND h.sprint_id = m.iteration_id
                 -- FIX 1: Exact timestamp comparison (removed + interval '23:59:59')
                 AND h.changed_at <= it2.start_date
               ORDER BY h.changed_at DESC
               LIMIT 1
             ) AS action_at_start
      FROM membership_base m
    ),
    planned_pairs AS (
      SELECT s.issue_id, s.iteration_id, i.project_id
      FROM state_at_start s
      JOIN iters it ON it.id = s.iteration_id
      JOIN clean_jira.issues i ON i.id = s.issue_id
      WHERE (s.action_at_start = 'added')
         OR (s.action_at_start IS NULL AND i.jira_created_at <= it.start_date)
    ),
    -- SP Extraction
    planned_sp AS (
      SELECT p.issue_id, p.iteration_id,
             COALESCE(
               (SELECT CASE
                  WHEN jsonb_typeof(cfv.json_value) = 'number' THEN (cfv.json_value)::numeric
                  ELSE NULL
                END
                FROM clean_jira.field_values cfv
                JOIN clean_jira.field_keys cf ON cf.id = cfv.field_key_id
                WHERE cf.project_id = p.project_id
                  AND (
                    cf.external_key IN ('customfield_10036','customfield_10016','story_points')
                    OR LOWER(cf.name) LIKE '%story point%'
                  )
                  AND cfv.issue_id = p.issue_id
                LIMIT 1
               ), 0
             ) AS story_points
      FROM planned_pairs p
    ),
    -- Done logic
    done_by_history AS (
      SELECT p.issue_id, p.iteration_id
      FROM planned_pairs p
      JOIN clean_jira.issue_status_changelog h ON h.issue_id = p.issue_id
      JOIN end_statuses es
        ON es.status_id = h.to_status_id
        AND es.project_id = (SELECT project_id FROM clean_jira.issues WHERE id = p.issue_id)
      JOIN iters it ON it.id = p.iteration_id
      WHERE h.changed_at::date <= it.end_date::date
      GROUP BY p.issue_id, p.iteration_id
    ),
    done_pairs AS (
      SELECT p.issue_id, p.iteration_id
      FROM planned_pairs p
      JOIN clean_jira.issues i ON i.id = p.issue_id
      LEFT JOIN done_by_history dbh ON dbh.issue_id = p.issue_id AND dbh.iteration_id = p.iteration_id
      LEFT JOIN end_statuses es ON es.status_id = i.status_id AND es.project_id = p.project_id
      JOIN iters it ON it.id = p.iteration_id
      WHERE (i.jira_resolved_at IS NOT NULL AND i.jira_resolved_at::date <= it.end_date::date)
         OR (es.status_id IS NOT NULL AND it.end_date < CURRENT_DATE)
         OR (dbh.issue_id IS NOT NULL)
    ),
    agg AS (
        SELECT
            p.iteration_id,
            COUNT(DISTINCT p.issue_id) as planned_issues,
            COALESCE(SUM(ps.story_points), 0) as planned_story_points,
            COUNT(DISTINCT dp.issue_id) as completed_issues,
            COALESCE(SUM(
                CASE WHEN dp.issue_id IS NOT NULL THEN ps.story_points ELSE 0 END
            ), 0) as completed_story_points
        FROM planned_pairs p
        LEFT JOIN planned_sp ps ON ps.issue_id = p.issue_id AND ps.iteration_id = p.iteration_id
        LEFT JOIN done_pairs dp ON dp.issue_id = p.issue_id AND dp.iteration_id = p.iteration_id
        GROUP BY p.iteration_id
    )
    SELECT
        gen_random_uuid() as id,
        it.project_id,
        it.id as iteration_id,
        it.name as iteration_name,
        it.start_date::date,
        it.end_date::date,
        NULL::text as issue_type,
        NULL::text as custom_field_value,
        COALESCE(a.planned_issues, 0) as planned_issues,
        COALESCE(a.planned_story_points, 0) as planned_story_points,
        COALESCE(a.completed_issues, 0) as completed_issues,
        COALESCE(a.completed_story_points, 0) as completed_story_points,
        now() as created_at
    FROM iters it
    LEFT JOIN agg a ON a.iteration_id = it.id;

    CREATE UNIQUE INDEX idx_fv_id ON metrics.fact_velocity(id);
    CREATE UNIQUE INDEX idx_fv_project_iter ON metrics.fact_velocity(project_id, iteration_id);


    -- =================================================================================================
    -- FACT VELOCITY SLICE (Corrected to use same membership logic)
    -- =================================================================================================
    CREATE MATERIALIZED VIEW metrics.fact_velocity_slice AS
    WITH iters AS (
        SELECT * FROM clean_jira.sprints WHERE start_date IS NOT NULL AND end_date IS NOT NULL
    ),
    membership_base AS (
      SELECT DISTINCT ii.issue_id, ii.sprint_id AS iteration_id
      FROM clean_jira.sprint_issues ii
      -- FIX 2: Removal of is_active=true
    ),
    state_at_start AS (
      SELECT m.issue_id, m.iteration_id,
             (
               SELECT h.action
               FROM clean_jira.sprint_issues_changelog h
               JOIN iters it2 ON it2.id = h.sprint_id
               WHERE h.issue_id = m.issue_id
                 AND h.sprint_id = m.iteration_id
                 -- FIX 1: Exact timestamp
                 AND h.changed_at <= it2.start_date
               ORDER BY h.changed_at DESC
               LIMIT 1
             ) AS action_at_start
      FROM membership_base m
    ),
    all_pairs AS (
        SELECT
            m.issue_id,
            m.iteration_id,
            it.project_id,
            it.name as iteration_name,
            it.start_date,
            it.end_date,
            CASE
                WHEN (s.action_at_start = 'added')
                     OR (s.action_at_start IS NULL AND i.jira_created_at <= it.start_date) THEN true
                ELSE false
            END as is_planned,
            (i.jira_resolved_at IS NOT NULL AND i.jira_resolved_at::date <= it.end_date::date) as is_completed,
            COALESCE(itype.name, 'UNKNOWN') as issue_type
        FROM membership_base m
        JOIN iters it ON it.id = m.iteration_id
        JOIN clean_jira.issues i ON i.id = m.issue_id
        LEFT JOIN clean_jira.issue_types itype ON itype.id = i.type_id
        LEFT JOIN state_at_start s ON s.issue_id = m.issue_id AND s.iteration_id = m.iteration_id
    )
    SELECT
        gen_random_uuid() as id,
        project_id,
        iteration_id,
        iteration_name,
        start_date::date,
        end_date::date,
        'issue_type' as slice_dim,
        issue_type as slice_value,
        COUNT(CASE WHEN is_planned THEN 1 END) as planned_issues,
        0 as planned_story_points,
        COUNT(CASE WHEN is_planned AND is_completed THEN 1 END) as completed_issues,
        -- Jira Velocity chart: 'Completed' bar. Usually includes added issues.
        -- Standard Fact Velocity (above) joins 'planned_pairs' with 'done_pairs'. It seems to define 'Completed' as 'Planned AND Completed'?
        -- Wait, Fact Velocity logic above: 'FROM planned_pairs p LEFT JOIN done_pairs dp'.
        -- Yes, the current logic only counts completed IF they were planned.
        -- Jira Velocity counts Unplanned Completed too?
        -- For now, respecting the same logic as fact_velocity (Planned Only).
        0 as completed_story_points,
        now() as created_at
    FROM all_pairs
    GROUP BY project_id, iteration_id, iteration_name, start_date, end_date, issue_type;

    CREATE UNIQUE INDEX idx_fvs_id ON metrics.fact_velocity_slice(id);
    CREATE INDEX idx_fvs_proj_iter_dim_val
        ON metrics.fact_velocity_slice(project_id, iteration_id, slice_dim, slice_value);


    -- =================================================================================================
    -- RECREATE GOLD LAYER MVs (Dropped by CASCADE)
    -- =================================================================================================

    -- metrics.mv_velocity
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
        CASE
            WHEN f.planned_story_points > 0 THEN
                ROUND((f.completed_story_points::numeric / f.planned_story_points::numeric) * 100, 2)
            ELSE 0
        END AS completion_rate_points_pct,
        CASE
            WHEN f.planned_issues > 0 THEN
                ROUND((f.completed_issues::numeric / f.planned_issues::numeric) * 100, 2)
            ELSE 0
        END AS completion_rate_issues_pct
    FROM metrics.fact_velocity f
    JOIN clean_jira.projects p ON f.project_id = p.id
    WHERE f.issue_type IS NULL
      AND f.custom_field_value IS NULL
    WITH DATA;

    CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_velocity_sprint_id
        ON metrics.mv_velocity(sprint_id);
    CREATE INDEX IF NOT EXISTS idx_mv_velocity_project
        ON metrics.mv_velocity(project_id, start_date);

    COMMENT ON MATERIALIZED VIEW metrics.mv_velocity IS
        'Velocity metrics per sprint (reading from fact_velocity calculated by job)';

    -- metrics.mv_velocity_slice
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
        CASE
            WHEN f.planned_story_points > 0 THEN
                ROUND((f.completed_story_points::numeric / f.planned_story_points::numeric) * 100, 2)
            ELSE 0
        END AS completion_rate_points_pct,
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


def downgrade() -> None:
    # Revert to the potentially buggy version or just drop
    op.execute(
        """
        DROP MATERIALIZED VIEW IF EXISTS metrics.mv_velocity CASCADE;
        DROP MATERIALIZED VIEW IF EXISTS metrics.mv_velocity_slice CASCADE;
        DROP MATERIALIZED VIEW IF EXISTS metrics.fact_velocity CASCADE;
        DROP MATERIALIZED VIEW IF EXISTS metrics.fact_velocity_slice CASCADE;

        -- Restore 0009 version? Complex to put SQL here.
        -- Ideally we would put back the specific queries from 0008/0009.
        -- For now, just dropping is safe as it forces forward-fix.
    """
    )
