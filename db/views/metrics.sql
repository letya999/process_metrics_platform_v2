-- ============================================================================
-- METRICS SCHEMA - Materialized Views for BI
-- Purpose: Pre-aggregated metrics for Lead Time, Velocity, Throughput
-- Refresh: After each data sync via Dagster assets
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS metrics;

COMMENT ON SCHEMA metrics IS 'Materialized views for team metrics (Lead Time, Velocity, Throughput)';

-- ============================================================================
-- MATERIALIZED VIEW: mv_lead_time
-- Purpose: Lead time per issue (time from creation to resolution)
-- ============================================================================

CREATE MATERIALIZED VIEW IF NOT EXISTS metrics.mv_lead_time AS
SELECT
    i.id AS issue_id,
    i.external_key AS issue_key,
    i.summary,
    i.project_id,
    p.external_key AS project_key,
    p.name AS project_name,
    it.name AS issue_type,
    it.hierarchy_level,
    ist.name AS status_name,
    ist.category AS status_category,
    i.jira_created_at,
    i.jira_resolved_at,
    -- Lead time in days (NULL if not resolved)
    CASE
        WHEN i.jira_resolved_at IS NOT NULL THEN
            EXTRACT(EPOCH FROM (i.jira_resolved_at - i.jira_created_at)) / 86400.0
        ELSE NULL
    END AS lead_time_days,
    -- Lead time in hours
    CASE
        WHEN i.jira_resolved_at IS NOT NULL THEN
            EXTRACT(EPOCH FROM (i.jira_resolved_at - i.jira_created_at)) / 3600.0
        ELSE NULL
    END AS lead_time_hours,
    i.db_updated_at
FROM clean_jira.issues i
JOIN clean_jira.projects p ON i.project_id = p.id
JOIN clean_jira.issue_types it ON i.type_id = it.id
JOIN clean_jira.issue_statuses ist ON i.status_id = ist.id
WHERE ist.category = 'done'  -- Only resolved issues
WITH DATA;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_lead_time_issue_id
    ON metrics.mv_lead_time(issue_id);
CREATE INDEX IF NOT EXISTS idx_mv_lead_time_project
    ON metrics.mv_lead_time(project_id, jira_resolved_at);
CREATE INDEX IF NOT EXISTS idx_mv_lead_time_type
    ON metrics.mv_lead_time(issue_type);

COMMENT ON MATERIALIZED VIEW metrics.mv_lead_time IS
    'Lead time per resolved issue (creation to resolution)';

-- ============================================================================
-- MATERIALIZED VIEW: mv_velocity
-- Purpose: Velocity per sprint (issues and story points completed)
-- ============================================================================

CREATE MATERIALIZED VIEW IF NOT EXISTS metrics.mv_velocity AS
SELECT
    s.id AS sprint_id,
    s.external_id AS sprint_external_id,
    s.name AS sprint_name,
    s.project_id,
    p.external_key AS project_key,
    p.name AS project_name,
    s.status AS sprint_status,
    s.start_date,
    s.end_date,
    s.complete_date,
    -- Count of issues in sprint
    COUNT(DISTINCT si.issue_id) AS total_issues,
    -- Count of completed issues
    COUNT(DISTINCT CASE WHEN ist.category = 'done' THEN si.issue_id END) AS completed_issues,
    -- Completion rate
    CASE
        WHEN COUNT(DISTINCT si.issue_id) > 0 THEN
            ROUND(
                COUNT(DISTINCT CASE WHEN ist.category = 'done' THEN si.issue_id END)::NUMERIC /
                COUNT(DISTINCT si.issue_id) * 100,
                2
            )
        ELSE 0
    END AS completion_rate_pct
FROM clean_jira.sprints s
JOIN clean_jira.projects p ON s.project_id = p.id
LEFT JOIN clean_jira.sprint_issues si ON s.id = si.sprint_id AND si.is_active = true
LEFT JOIN clean_jira.issues i ON si.issue_id = i.id
LEFT JOIN clean_jira.issue_statuses ist ON i.status_id = ist.id
GROUP BY s.id, s.external_id, s.name, s.project_id, p.external_key, p.name,
         s.status, s.start_date, s.end_date, s.complete_date
WITH DATA;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_velocity_sprint_id
    ON metrics.mv_velocity(sprint_id);
CREATE INDEX IF NOT EXISTS idx_mv_velocity_project
    ON metrics.mv_velocity(project_id, start_date);
CREATE INDEX IF NOT EXISTS idx_mv_velocity_status
    ON metrics.mv_velocity(sprint_status);

COMMENT ON MATERIALIZED VIEW metrics.mv_velocity IS
    'Velocity metrics per sprint (issue counts and completion rate)';

-- ============================================================================
-- MATERIALIZED VIEW: mv_throughput
-- Purpose: Daily throughput (issues completed per day)
-- ============================================================================

CREATE MATERIALIZED VIEW IF NOT EXISTS metrics.mv_throughput AS
SELECT
    DATE(i.jira_resolved_at) AS resolved_date,
    i.project_id,
    p.external_key AS project_key,
    p.name AS project_name,
    it.name AS issue_type,
    it.hierarchy_level,
    -- Count of issues resolved on this date
    COUNT(*) AS issues_completed,
    -- Average lead time for issues resolved on this date
    ROUND(
        AVG(EXTRACT(EPOCH FROM (i.jira_resolved_at - i.jira_created_at)) / 86400.0)::NUMERIC,
        2
    ) AS avg_lead_time_days
FROM clean_jira.issues i
JOIN clean_jira.projects p ON i.project_id = p.id
JOIN clean_jira.issue_types it ON i.type_id = it.id
JOIN clean_jira.issue_statuses ist ON i.status_id = ist.id
WHERE i.jira_resolved_at IS NOT NULL
  AND ist.category = 'done'
GROUP BY DATE(i.jira_resolved_at), i.project_id, p.external_key, p.name,
         it.name, it.hierarchy_level
WITH DATA;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_throughput_date_project_type
    ON metrics.mv_throughput(resolved_date, project_id, issue_type);
CREATE INDEX IF NOT EXISTS idx_mv_throughput_project
    ON metrics.mv_throughput(project_id, resolved_date);

COMMENT ON MATERIALIZED VIEW metrics.mv_throughput IS
    'Daily throughput (issues completed per day by type)';

-- ============================================================================
-- REFRESH FUNCTION
-- Purpose: Refresh all metrics views (called by Dagster)
-- ============================================================================

CREATE OR REPLACE FUNCTION metrics.refresh_all_views()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY metrics.mv_lead_time;
    REFRESH MATERIALIZED VIEW CONCURRENTLY metrics.mv_velocity;
    REFRESH MATERIALIZED VIEW CONCURRENTLY metrics.mv_throughput;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION metrics.refresh_all_views() IS
    'Refresh all metrics materialized views (use after data sync)';
