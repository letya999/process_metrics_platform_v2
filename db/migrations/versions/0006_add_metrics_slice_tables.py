"""add_metrics_slice_tables

Revision ID: 0006
Revises: 0005
Create Date: 2025-12-14 01:25:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0006_add_metrics_slice_tables"
down_revision = "0005_add_default_jira_project"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Using raw SQL to define Materialized Views with embedded logic
    # This replaces the empty tables + Python population logic

    op.execute(
        """
    -- Cleanup potential leftovers/mismatches
    DROP TABLE IF EXISTS metrics.fact_lead_time_bins_slice CASCADE;
    DROP TABLE IF EXISTS metrics.fact_lead_time_slice CASCADE;
    DROP TABLE IF EXISTS metrics.fact_lead_time_bins CASCADE;
    DROP TABLE IF EXISTS metrics.fact_lead_time CASCADE;
    DROP TABLE IF EXISTS metrics.fact_velocity_slice CASCADE;
    DROP TABLE IF EXISTS metrics.fact_velocity CASCADE;
    DROP TABLE IF EXISTS metrics.metric_slice_rules CASCADE;

    DROP MATERIALIZED VIEW IF EXISTS metrics.fact_lead_time_bins_slice CASCADE;
    DROP MATERIALIZED VIEW IF EXISTS metrics.fact_lead_time_slice CASCADE;
    DROP MATERIALIZED VIEW IF EXISTS metrics.fact_lead_time_bins CASCADE;
    DROP MATERIALIZED VIEW IF EXISTS metrics.fact_lead_time CASCADE;
    DROP MATERIALIZED VIEW IF EXISTS metrics.fact_velocity_slice CASCADE;
    DROP MATERIALIZED VIEW IF EXISTS metrics.fact_velocity CASCADE;

    -- =================================================================================================
    -- METRIC SLICE RULES (Configuration Table - stays a table)
    -- =================================================================================================
    CREATE TABLE metrics.metric_slice_rules (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        project_id UUID,
        metric TEXT NOT NULL,
        slice_dim TEXT NOT NULL,
        enabled BOOLEAN DEFAULT true,
        top_n INTEGER DEFAULT 10,
        group_other BOOLEAN DEFAULT true,
        max_distinct INTEGER DEFAULT 50,
        created_at TIMESTAMPTZ DEFAULT now(),

        CONSTRAINT uq_metric_slice_rules_project_metric_dim UNIQUE (project_id, metric, slice_dim)
    );

    -- =================================================================================================
    -- VELOCITY CALCULATIONS (Materialized Views)
    -- =================================================================================================

    CREATE MATERIALIZED VIEW metrics.fact_velocity AS
    WITH params AS (
      -- We calculate for ALL projects in the MV, unlike Python loop
      SELECT id AS project_id FROM clean_jira.projects
    ),
    iters AS (
      SELECT it.*
      FROM clean_jira.sprints it
      WHERE it.start_date IS NOT NULL AND it.end_date IS NOT NULL
    ),
    end_statuses AS (
       -- Identify "Done" statuses based on board columns containing 'Done'
       -- Joined with project to be specific
      SELECT DISTINCT s.id AS status_id, b.project_id
      FROM clean_jira.board_columns bc
      JOIN clean_jira.board_column_statuses bcs ON bcs.board_column_id = bc.id
      JOIN clean_jira.issue_statuses s          ON s.id = bcs.status_id
      JOIN clean_jira.boards b                  ON b.id = bc.board_id
      WHERE bc.name ILIKE '%Done%'
    ),
    membership_base AS (
      SELECT DISTINCT ii.issue_id, ii.sprint_id AS iteration_id
      FROM clean_jira.sprint_issues ii
      WHERE ii.is_active = true
    ),
    state_at_start AS (
      SELECT m.issue_id, m.iteration_id,
             (
               SELECT h.action
               FROM clean_jira.sprint_issues_changelog h
               JOIN iters it2 ON it2.id = h.sprint_id
               WHERE h.issue_id = m.issue_id
                 AND h.sprint_id = m.iteration_id
                 AND h.changed_at <= (it2.start_date + interval '23:59:59')
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
         OR (s.action_at_start IS NULL AND i.jira_created_at::date <= it.start_date::date)
    ),
    -- Simple story points extraction (current only for MVP performance in SQL)
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
                  AND (cf.external_key IN ('customfield_10036','customfield_10016','story_points') OR LOWER(cf.name) LIKE '%story point%')
                  AND cfv.issue_id = p.issue_id
                LIMIT 1
               ), 0
             ) AS story_points
      FROM planned_pairs p
    ),
    done_pairs AS (
      SELECT p.issue_id, p.iteration_id
      FROM planned_pairs p
      JOIN clean_jira.issues i ON i.id = p.issue_id
      LEFT JOIN end_statuses es ON es.status_id = i.status_id AND es.project_id = p.project_id
      JOIN iters it ON it.id = p.iteration_id
      -- Check if resolved or in Done status
      WHERE (i.jira_resolved_at IS NOT NULL AND i.jira_resolved_at::date <= it.end_date::date)
         OR (es.status_id IS NOT NULL)
    ),
    agg AS (
        SELECT
            p.iteration_id,
            COUNT(DISTINCT p.issue_id) as planned_issues,
            COALESCE(SUM(ps.story_points), 0) as planned_story_points,
            COUNT(DISTINCT dp.issue_id) as completed_issues,
            COALESCE(SUM(CASE WHEN dp.issue_id IS NOT NULL THEN ps.story_points ELSE 0 END), 0) as completed_story_points
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

    CREATE UNIQUE INDEX idx_fv_project_iter ON metrics.fact_velocity(project_id, iteration_id);


    CREATE MATERIALIZED VIEW metrics.fact_velocity_slice AS
    WITH iters AS (
        SELECT * FROM clean_jira.sprints WHERE start_date IS NOT NULL AND end_date IS NOT NULL
    ),
    -- Re-using similar logic but grouping by issue type
    base_data AS (
        SELECT
            it.project_id,
            it.id as iteration_id,
            it.name as iteration_name,
            it.start_date,
            it.end_date,
            i.id as issue_id,
            COALESCE(itype.name, 'UNKNOWN') as slice_value,
            -- Determine if planned (simplified logic: added before start or created before start)
            true as is_planned, -- Simplifying for MV performance, assuming all sprint issues are planned for now
            -- Determine if completed
            (i.jira_resolved_at IS NOT NULL AND i.jira_resolved_at::date <= it.end_date::date) as is_completed
        FROM clean_jira.sprint_issues si
        JOIN iters it ON it.id = si.sprint_id
        JOIN clean_jira.issues i ON i.id = si.issue_id
        LEFT JOIN clean_jira.issue_types itype ON itype.id = i.type_id
        WHERE si.is_active = true
    )
    SELECT
        gen_random_uuid() as id,
        project_id,
        iteration_id,
        iteration_name,
        start_date::date,
        end_date::date,
        'issue_type' as slice_dim,
        slice_value,
        COUNT(*) as planned_issues, -- Placeholder logic
        0 as planned_story_points,
        COUNT(CASE WHEN is_completed THEN 1 END) as completed_issues,
        0 as completed_story_points,
        now() as created_at
    FROM base_data
    GROUP BY project_id, iteration_id, iteration_name, start_date, end_date, slice_value;

    -- Concurrency requires unique index on 'id'
    CREATE UNIQUE INDEX idx_fvs_id ON metrics.fact_velocity_slice(id);
    CREATE INDEX idx_fvs_proj_iter_dim_val ON metrics.fact_velocity_slice(project_id, iteration_id, slice_dim, slice_value);


    -- =================================================================================================
    -- 4. LEAD TIME MVs
    -- =================================================================================================

    CREATE MATERIALIZED VIEW metrics.fact_lead_time AS
    WITH issues_src AS (
        SELECT i.id AS issue_id, i.project_id, i.jira_created_at as created, i.jira_resolved_at as resolved
        FROM clean_jira.issues i
        WHERE i.jira_resolved_at IS NOT NULL
    ),
    -- Calculate lead time simply as Resolved - Created for now (Classic Lead Time)
    -- The fancy "Board Column" logic is rigorous but fails if board config is messy.
    -- We'll use the robust simple metric for the MV first.
    calc AS (
        SELECT
            issue_id,
            project_id,
            created,
            resolved,
            EXTRACT(EPOCH FROM (resolved - created))/86400.0 AS lead_time_days
        FROM issues_src
    ),
    bins AS (
         SELECT
            issue_id,
            GREATEST(1, CEIL(lead_time_days))::int AS bin_number
         FROM calc
    )
    SELECT
        gen_random_uuid() as id,
        c.project_id,
        c.issue_id,
        c.lead_time_days,
        c.lead_time_days * 24 as lead_time_hours,
        c.created as commitment_start_at,
        c.resolved as commitment_end_at,
        NULL::uuid as start_status_commitment_point_id,
        NULL::uuid as end_status_commitment_point_id,
        NULL::uuid as lead_time_bin_id, -- Linked later or calculated on fly
        b.bin_number, -- Helper column
        now() as created_at
    FROM calc c
    JOIN bins b ON b.issue_id = c.issue_id;

    -- Concurrency requires unique index on 'id'
    CREATE UNIQUE INDEX idx_flt_id ON metrics.fact_lead_time(id);
    CREATE UNIQUE INDEX idx_flt_project_issue ON metrics.fact_lead_time(project_id, issue_id);


    CREATE MATERIALIZED VIEW metrics.fact_lead_time_bins AS
    SELECT
        gen_random_uuid() as id,
        project_id,
        bin_number,
        COUNT(*) as tickets_count,
        now() as created_at
    FROM metrics.fact_lead_time
    GROUP BY project_id, bin_number;

    -- Concurrency requires unique index on 'id'
    CREATE UNIQUE INDEX idx_fltb_id ON metrics.fact_lead_time_bins(id);
    CREATE UNIQUE INDEX idx_fltb_project_bin ON metrics.fact_lead_time_bins(project_id, bin_number);

    -- Sliced Views (MVP placeholder logic pointing to base tables)
    CREATE MATERIALIZED VIEW metrics.fact_lead_time_slice AS
    SELECT
        gen_random_uuid() as id,
        f.project_id,
        f.issue_id,
        NULL::uuid as iteration_id,
        f.lead_time_days,
        f.commitment_start_at,
        f.commitment_end_at,
        f.start_status_commitment_point_id,
        f.end_status_commitment_point_id,
        NULL::uuid as lead_time_bin_id,
        'issue_type' as slice_dim,
        COALESCE(it.name, 'UNKNOWN') as slice_value,
        now() as created_at
    FROM metrics.fact_lead_time f
    JOIN clean_jira.issues i ON i.id = f.issue_id
    LEFT JOIN clean_jira.issue_types it ON it.id = i.type_id;

    -- Concurrency requires unique index on 'id'
    CREATE UNIQUE INDEX idx_lts_id ON metrics.fact_lead_time_slice(id);
    CREATE INDEX idx_lts_proj_iter_dim_val ON metrics.fact_lead_time_slice(project_id, slice_dim, slice_value);

    CREATE MATERIALIZED VIEW metrics.fact_lead_time_bins_slice AS
    SELECT
        gen_random_uuid() as id,
        project_id,
        slice_dim,
        slice_value,
        GREATEST(1, CEIL(lead_time_days))::int as bin_number,
        COUNT(*) as tickets_count,
        now() as created_at
    FROM metrics.fact_lead_time_slice
    GROUP BY project_id, slice_dim, slice_value, GREATEST(1, CEIL(lead_time_days))::int;

    -- Concurrency requires unique index on 'id'
    CREATE UNIQUE INDEX idx_ltb_slices_id ON metrics.fact_lead_time_bins_slice(id);
    CREATE INDEX idx_ltb_slices_proj_dim_val_bin ON metrics.fact_lead_time_bins_slice(project_id, slice_dim, slice_value, bin_number);
    """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP MATERIALIZED VIEW IF EXISTS metrics.fact_lead_time_bins_slice CASCADE;
        DROP MATERIALIZED VIEW IF EXISTS metrics.fact_lead_time_slice CASCADE;
        DROP MATERIALIZED VIEW IF EXISTS metrics.fact_lead_time_bins CASCADE;
        DROP MATERIALIZED VIEW IF EXISTS metrics.fact_lead_time CASCADE;
        DROP MATERIALIZED VIEW IF EXISTS metrics.fact_velocity_slice CASCADE;
        DROP MATERIALIZED VIEW IF EXISTS metrics.fact_velocity CASCADE;
        DROP TABLE IF EXISTS metrics.metric_slice_rules CASCADE;

        DROP TABLE IF EXISTS clean_jira.issue_status_changelog CASCADE;
    """
    )
