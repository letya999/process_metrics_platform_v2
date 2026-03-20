-- ============================================================================
-- METRICS SCHEMA - Unified Views over Generic Fact Store
-- Purpose: Presentation layer for BI tools (Metabase, etc.)
-- ============================================================================

-- 1. Velocity View (Aggregation by Sprint)
CREATE OR REPLACE VIEW metrics.mv_velocity AS
WITH sprint_metrics AS (
    SELECT
        project_key, entity_id AS sprint_id, entity_type, full_date,
        MAX(CASE WHEN calc_code = 'velocity_planned_sp' THEN value END) as planned_story_points,
        MAX(CASE WHEN calc_code = 'velocity_completed_sp' THEN value END) as completed_story_points,
        MAX(CASE WHEN calc_code = 'velocity_planned_count' THEN value END) as planned_issues,
        MAX(CASE WHEN calc_code = 'velocity_completed_count' THEN value END) as completed_issues
    FROM metrics.v_facts
    WHERE metric_code = 'velocity' AND slice_rule_name IS NULL
    GROUP BY project_key, entity_id, entity_type, full_date
)
SELECT
    sm.*,
    CASE WHEN sm.planned_story_points > 0 THEN sm.completed_story_points / sm.planned_story_points * 100 ELSE 0 END as completion_rate_points_pct,
    CASE WHEN sm.planned_issues > 0 THEN sm.completed_issues / sm.planned_issues * 100 ELSE 0 END as completion_rate_issues_pct
FROM sprint_metrics sm;

-- 2. Lead Time View (Per Issue)
CREATE OR REPLACE VIEW metrics.mv_lead_time AS
SELECT
    project_key, entity_id AS issue_key, value AS lead_time_days,
    event_start_at AS commitment_start_at, event_end_at AS commitment_end_at,
    slice_value as issue_type -- if issue_type rule was applied or from base
FROM metrics.v_facts
WHERE calc_code = 'lead_time_days' AND slice_rule_name IS NULL;

-- 3. Throughput View (Weekly)
CREATE OR REPLACE VIEW metrics.mv_throughput AS
SELECT
    project_key, full_date AS week_start_date, value AS issues_completed
FROM metrics.v_facts
WHERE calc_code = 'throughput_count' AND slice_rule_name IS NULL;

-- 4. CFD View (Daily Snapshot)
CREATE OR REPLACE VIEW metrics.mv_cfd AS
SELECT
    f.project_key, f.full_date as date, f.value as issue_count,
    bc.name as status_name, bc.position as column_position
FROM metrics.v_facts f
LEFT JOIN clean_jira.board_columns bc ON f.entity_id = bc.id::text
WHERE f.calc_code = 'cfd_count';

-- 5. Backlog Health View (Daily Snapshot)
CREATE OR REPLACE VIEW metrics.mv_backlog_health AS
SELECT
    project_key, full_date as date,
    MAX(CASE WHEN calc_code = 'backlog_size' THEN value END) as total_backlog_size,
    MAX(CASE WHEN calc_code = 'backlog_created' THEN value END) as created_daily,
    MAX(CASE WHEN calc_code = 'backlog_resolved' THEN value END) as resolved_daily,
    MAX(CASE WHEN calc_code = 'backlog_net_growth' THEN value END) as net_growth_daily
FROM metrics.v_facts
WHERE metric_code = 'backlog_growth' AND slice_rule_name IS NULL
GROUP BY project_key, full_date;

-- 6. Generic Sliced View (For all metrics)
CREATE OR REPLACE VIEW metrics.mv_sliced_metrics AS
SELECT
    project_key, metric_code, calc_code, slice_rule_name, slice_value,
    full_date as date, value, unit_code
FROM metrics.v_facts
WHERE slice_rule_name IS NOT NULL;

-- 7. Advanced: Flow Efficiency
CREATE OR REPLACE VIEW metrics.mv_flow_efficiency AS
SELECT
    project_key, entity_id as issue_key,
    MAX(CASE WHEN calc_code = 'flow_active_days' THEN value END) as active_days,
    MAX(CASE WHEN calc_code = 'flow_wait_days' THEN value END) as wait_days,
    MAX(CASE WHEN calc_code = 'flow_efficiency_pct' THEN value END) as efficiency_pct,
    event_end_at as completion_date
FROM metrics.v_facts
WHERE metric_code = 'flow_efficiency'
GROUP BY project_key, entity_id, event_end_at;

-- Compatibility / Legacy Refresh (Now No-op as these are standard views)
CREATE OR REPLACE FUNCTION metrics.refresh_all_views()
RETURNS void AS $$
BEGIN
    -- No-op for standard views
    RETURN;
END;
$$ LANGUAGE plpgsql;
