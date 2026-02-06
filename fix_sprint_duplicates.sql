-- 1. Очищаем таблицу спринтов (каскадно удалит и sprint_issues)
TRUNCATE TABLE clean_jira.sprints RESTART IDENTITY CASCADE;

-- 2. Заполняем спринты заново (ТОЛЬКО уникальные, через DISTINCT ON)
INSERT INTO clean_jira.sprints (
    project_id,
    external_id,
    name,
    goal,
    status,
    start_date,
    end_date,
    complete_date,
    updated_at
)
SELECT DISTINCT ON (p.id, s.id::text)
    p.id as project_id,
    s.id::text as external_id,
    s.name,
    s.goal,
    CASE s.state
        WHEN 'future' THEN 'future'::clean_jira.sprint_status
        WHEN 'active' THEN 'active'::clean_jira.sprint_status
        WHEN 'closed' THEN 'closed'::clean_jira.sprint_status
        ELSE 'future'::clean_jira.sprint_status
    END as status,
    s.start_date::timestamptz as start_date,
    s.end_date::timestamptz as end_date,
    s.complete_date::timestamptz as complete_date,
    now() as updated_at
FROM raw_jira.sprints s
JOIN raw_jira.board_configurations bc ON s.board_id = bc.board_id
JOIN clean_jira.projects p ON bc.project_key = p.external_key
WHERE s.id IS NOT NULL;

-- 3. Восстанавливаем sprint_issues из changelog (Logic from clean_jira_sprint_issues)
WITH changelog_events AS (
    -- Extract Sprint changes from changelog
    SELECT
        r.id::text as issue_external_id,
        r.fields__project__id::text as project_external_id,
        h.created::timestamptz as changed_at,
        item."to" as to_value,
        item."from" as from_value,
        h.author__account_id as author_id
    FROM raw_jira.issues__changelog__histories__items item
    JOIN raw_jira.issues__changelog__histories h
        ON item._dlt_parent_id = h._dlt_id
    JOIN raw_jira.issues r ON h._dlt_parent_id = r._dlt_id
    WHERE item.field = 'Sprint'
),
-- Split comma-separated sprint IDs for 'added' actions
added_events AS (
    SELECT
        issue_external_id,
        project_external_id,
        changed_at,
        trim(sprint_id) as sprint_external_id,
        'added' as action,
        author_id
    FROM changelog_events
    CROSS JOIN LATERAL regexp_split_to_table(
        COALESCE(to_value, ''), '\s*,\s*'
    ) as sprint_id
    WHERE to_value IS NOT NULL AND to_value != ''
),
-- Split comma-separated sprint IDs for 'removed' actions
removed_events AS (
    SELECT
        issue_external_id,
        project_external_id,
        changed_at,
        trim(sprint_id) as sprint_external_id,
        'removed' as action,
        author_id
    FROM changelog_events
    CROSS JOIN LATERAL regexp_split_to_table(
        COALESCE(from_value, ''), '\s*,\s*'
    ) as sprint_id
    WHERE from_value IS NOT NULL AND from_value != ''
),
-- Extract sprint data from current issue fields (Snapshot/Backfill)
snapshot_events AS (
    SELECT
        i.id::text as issue_external_id,
        i.fields__project__id::text as project_external_id,
        COALESCE(i.fields__created::timestamptz, '1970-01-01'::timestamptz) as changed_at,
        s.id::text as sprint_external_id,
        'added' as action,
        NULL::text as author_id
    FROM raw_jira.issues i
    JOIN raw_jira.issues__fields__customfield_10020 s
      ON s._dlt_parent_id = i._dlt_id
    WHERE s.id IS NOT NULL
),
-- Union all events
all_events AS (
    SELECT issue_external_id, project_external_id, changed_at, sprint_external_id, action, author_id FROM added_events
    UNION ALL
    SELECT issue_external_id, project_external_id, changed_at, sprint_external_id, action, author_id FROM removed_events
    UNION ALL
    SELECT issue_external_id, project_external_id, changed_at, sprint_external_id, action, author_id::text FROM snapshot_events
),
-- Normalize sprint_external_id to actual sprint_id first
normalized_events AS (
    SELECT
        ae.issue_external_id,
        s.id as sprint_id,
        ae.changed_at,
        ae.action
    FROM all_events ae
    JOIN clean_jira.issues i ON i.external_id = ae.issue_external_id
    JOIN clean_jira.sprints s ON s.project_id = i.project_id
        AND (
            s.external_id = ae.sprint_external_id
            OR s.name = ae.sprint_external_id
        )
    WHERE ae.sprint_external_id IS NOT NULL
      AND ae.sprint_external_id != ''
),
-- Get the latest action for each issue-sprint pair
latest_action AS (
    SELECT DISTINCT ON (issue_external_id, sprint_id)
        issue_external_id,
        sprint_id,
        action,
        changed_at
    FROM normalized_events
    ORDER BY issue_external_id, sprint_id, changed_at DESC, action DESC
)
-- Insert only pairs where final action is 'added'
INSERT INTO clean_jira.sprint_issues (
    sprint_id,
    issue_id,
    is_active
)
SELECT
    la.sprint_id,
    i.id as issue_id,
    true as is_active
FROM latest_action la
JOIN clean_jira.issues i ON i.external_id = la.issue_external_id
WHERE la.action = 'added'
ON CONFLICT (sprint_id, issue_id) DO UPDATE SET
    is_active = EXCLUDED.is_active;
