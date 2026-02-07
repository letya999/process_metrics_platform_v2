"""fix schema inconsistencies

Revision ID: 0008_fix_schema_inconsistencies
Revises: 0007_add_issue_status_history
Create Date: 2025-12-14 00:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0008_fix_schema_inconsistencies"
down_revision = "0007_add_issue_status_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Fix Table Name (issue_status_history -> issue_status_changelog)
    op.execute(
        """
    DO $$
    BEGIN
        IF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'clean_jira' AND tablename = 'issue_status_history')
           AND NOT EXISTS (SELECT FROM pg_tables WHERE schemaname = 'clean_jira' AND tablename = 'issue_status_changelog') THEN
            ALTER TABLE clean_jira.issue_status_history RENAME TO issue_status_changelog;

            -- Rename indexes
            IF EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_cj_issue_status_history_issue') THEN
                ALTER INDEX clean_jira.idx_cj_issue_status_history_issue RENAME TO idx_cj_isc_issue;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_cj_issue_status_history_changed') THEN
                ALTER INDEX clean_jira.idx_cj_issue_status_history_changed RENAME TO idx_cj_isc_changed;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_cj_issue_status_history_to_status') THEN
                ALTER INDEX clean_jira.idx_cj_issue_status_history_to_status RENAME TO idx_cj_isc_to_status;
            END IF;
        END IF;
    END $$;
    """
    )

    # 2. Recreate MVs with Correct Logic and Indexes
    op.execute(
        """
    DROP MATERIALIZED VIEW IF EXISTS metrics.fact_lead_time_bins_slice CASCADE;
    DROP MATERIALIZED VIEW IF EXISTS metrics.fact_lead_time_slice CASCADE;
    DROP MATERIALIZED VIEW IF EXISTS metrics.fact_lead_time_bins CASCADE;
    DROP MATERIALIZED VIEW IF EXISTS metrics.fact_lead_time CASCADE;
    DROP MATERIALIZED VIEW IF EXISTS metrics.fact_velocity_slice CASCADE;
    DROP MATERIALIZED VIEW IF EXISTS metrics.fact_velocity CASCADE;

    -- VELOCITY
    CREATE MATERIALIZED VIEW metrics.fact_velocity AS
    WITH params AS (SELECT id AS project_id FROM clean_jira.projects),
    iters AS (
      SELECT it.* FROM clean_jira.sprints it WHERE it.start_date IS NOT NULL AND it.end_date IS NOT NULL
    ),
    end_statuses AS (
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
    done_by_history AS (
      SELECT p.issue_id, p.iteration_id
      FROM planned_pairs p
      JOIN clean_jira.issue_status_changelog h ON h.issue_id = p.issue_id
      JOIN end_statuses es ON es.status_id = h.to_status_id AND es.project_id = (SELECT project_id FROM clean_jira.issues WHERE id = p.issue_id)
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
         OR (es.status_id IS NOT NULL AND it.end_date < CURRENT_DATE) -- If sprint ended and current status is Done, assume done? Simplified logic.
         OR (dbh.issue_id IS NOT NULL)
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

    CREATE UNIQUE INDEX idx_fv_id ON metrics.fact_velocity(id);
    CREATE INDEX idx_fv_project_iter ON metrics.fact_velocity(project_id, iteration_id);

    -- VELOCITY SLICE
    CREATE MATERIALIZED VIEW metrics.fact_velocity_slice AS
    WITH iters AS (
        SELECT * FROM clean_jira.sprints WHERE start_date IS NOT NULL AND end_date IS NOT NULL
    ),
    base_data AS (
        SELECT
            it.project_id,
            it.id as iteration_id,
            it.name as iteration_name,
            it.start_date,
            it.end_date,
            i.id as issue_id,
            COALESCE(itype.name, 'UNKNOWN') as slice_value,
            true as is_planned,
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
        COUNT(*) as planned_issues,
        0 as planned_story_points,
        COUNT(CASE WHEN is_completed THEN 1 END) as completed_issues,
        0 as completed_story_points,
        now() as created_at
    FROM base_data
    GROUP BY project_id, iteration_id, iteration_name, start_date, end_date, slice_value;

    CREATE UNIQUE INDEX idx_fvs_id ON metrics.fact_velocity_slice(id);
    CREATE INDEX idx_fvs_proj_iter_dim_val ON metrics.fact_velocity_slice(project_id, iteration_id, slice_dim, slice_value);

    -- LEAD TIME
    CREATE MATERIALIZED VIEW metrics.fact_lead_time AS
    WITH params AS (SELECT id AS project_id FROM clean_jira.projects),
    points AS (
      SELECT s.project_id, s.board_id,
             s.board_column_id AS start_column_id, s.order_num AS start_order,
             e.board_column_id AS end_column_id, e.order_num AS end_order
      FROM (
          SELECT b.project_id, bc.board_id, bc.id AS board_column_id, bc.position as order_num
          FROM clean_jira.board_columns bc
          JOIN clean_jira.boards b ON b.id = bc.board_id
          WHERE bc.name ILIKE '%In Progress%'
      ) s
      JOIN (
          SELECT b.project_id, bc.board_id, bc.id AS board_column_id, bc.position as order_num
          FROM clean_jira.board_columns bc
          JOIN clean_jira.boards b ON b.id = bc.board_id
          WHERE bc.name ILIKE '%Done%'
      ) e ON e.project_id = s.project_id AND e.board_id = s.board_id
      WHERE s.order_num < e.order_num
    ),
    column_statuses AS (
      SELECT bc.id AS board_column_id, s.id AS status_id, bc.position as order_num
      FROM clean_jira.board_column_statuses bcs
      JOIN clean_jira.board_columns bc ON bc.id = bcs.board_column_id
      JOIN clean_jira.issue_statuses s ON s.id = bcs.status_id
    ),
    issues_src AS (
      SELECT i.id AS issue_id, i.project_id, i.jira_created_at as created, i.jira_resolved_at as resolved
      FROM clean_jira.issues i
    ),
    last_left_end AS (
      SELECT isrc.issue_id, MAX(h.changed_at) AS left_at
      FROM issues_src isrc
      JOIN clean_jira.issue_status_changelog h ON h.issue_id = isrc.issue_id
      JOIN points p ON p.project_id = isrc.project_id
      JOIN column_statuses cs_from ON cs_from.status_id = h.from_status_id
      WHERE cs_from.board_column_id = p.end_column_id
        AND NOT EXISTS (
            SELECT 1 FROM column_statuses cs2
            WHERE cs2.status_id = h.to_status_id
            AND cs2.board_column_id = p.end_column_id
        )
      GROUP BY isrc.issue_id
    ),
    end_event AS (
      SELECT isrc.issue_id,
             COALESCE(eh.end_at, isrc.resolved) AS end_at,
             NULL::uuid AS end_cp_id
      FROM issues_src isrc
      LEFT JOIN (
          SELECT DISTINCT ON (isrc.issue_id) isrc.issue_id, h.changed_at AS end_at
          FROM issues_src isrc
          LEFT JOIN last_left_end lle ON lle.issue_id = isrc.issue_id
          JOIN clean_jira.issue_status_changelog h ON h.issue_id = isrc.issue_id
          JOIN points p ON p.project_id = isrc.project_id
          JOIN column_statuses cs_to ON cs_to.status_id = h.to_status_id
          WHERE cs_to.board_column_id = p.end_column_id
            AND h.changed_at > COALESCE(lle.left_at, '-infinity')
            AND (isrc.resolved IS NULL OR h.changed_at <= isrc.resolved)
          ORDER BY isrc.issue_id, h.changed_at ASC
      ) eh ON eh.issue_id = isrc.issue_id
      WHERE COALESCE(eh.end_at, isrc.resolved) IS NOT NULL
    ),
    start_event AS (
      SELECT
        isrc.issue_id,
        COALESCE(sh.start_at, isrc.created) AS start_at,
        NULL::uuid AS start_cp_id
      FROM issues_src isrc
      JOIN end_event e ON e.issue_id = isrc.issue_id
      LEFT JOIN (
          SELECT DISTINCT ON (isrc.issue_id) isrc.issue_id, h.changed_at AS start_at
          FROM issues_src isrc
          JOIN end_event e ON e.issue_id = isrc.issue_id
          JOIN clean_jira.issue_status_changelog h ON h.issue_id = isrc.issue_id
          JOIN points p ON p.project_id = isrc.project_id
          JOIN column_statuses cs ON cs.status_id = h.to_status_id
          WHERE cs.order_num >= p.start_order AND cs.order_num < p.end_order
            AND h.changed_at <= e.end_at
          ORDER BY isrc.issue_id, h.changed_at ASC
      ) sh ON sh.issue_id = isrc.issue_id
      WHERE COALESCE(sh.start_at, isrc.created) IS NOT NULL
    ),
    calc AS (
      SELECT
        i.project_id,
        i.issue_id,
        s.start_at,
        e.end_at,
        EXTRACT(EPOCH FROM (e.end_at - s.start_at))/86400.0 AS lead_time_days
      FROM issues_src i
      JOIN start_event s ON s.issue_id = i.issue_id
      JOIN end_event   e ON e.issue_id = i.issue_id
      WHERE e.end_at >= s.start_at
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
        c.start_at as commitment_start_at,
        c.end_at as commitment_end_at,
        NULL::uuid as start_status_commitment_point_id,
        NULL::uuid as end_status_commitment_point_id,
        NULL::uuid as lead_time_bin_id,
        b.bin_number,
        now() as created_at
    FROM calc c
    JOIN bins b ON b.issue_id = c.issue_id;

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

    CREATE UNIQUE INDEX idx_fltb_id ON metrics.fact_lead_time_bins(id);
    CREATE UNIQUE INDEX idx_fltb_project_bin ON metrics.fact_lead_time_bins(project_id, bin_number);

    -- Slices
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
    """
    )
