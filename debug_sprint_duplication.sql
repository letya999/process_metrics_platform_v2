-- =====================================================
-- ДИАГНОСТИКА ДУБЛИРОВАНИЯ СПРИНТА "ADS Спринт 15"
-- =====================================================

-- 1. Проверяем проекты
SELECT
    id,
    external_key,
    name,
    created_at,
    updated_at
FROM clean_jira.projects
ORDER BY name;

-- 2. Проверяем записи спринта в clean_jira.sprints
SELECT
    s.id as sprint_id,
    s.project_id,
    p.external_key as project_key,
    p.name as project_name,
    s.name as sprint_name,
    s.start_date,
    s.end_date,
    s.complete_date,
    s.created_at,
    s.updated_at
FROM clean_jira.sprints s
LEFT JOIN clean_jira.projects p ON p.id = s.project_id
WHERE s.name = 'ADS Спринт 15'
ORDER BY s.project_id, s.created_at;

-- 3. Проверяем связи sprint_issues для этого спринта
SELECT
    si.sprint_id,
    p.external_key as project_key,
    p.name as project_name,
    COUNT(DISTINCT si.issue_id) as issues_count,
    COUNT(DISTINCT i.id) as valid_issues_count,
    STRING_AGG(DISTINCT it.name, ', ') as issue_types
FROM clean_jira.sprint_issues si
LEFT JOIN clean_jira.sprints s ON s.id = si.sprint_id
LEFT JOIN clean_jira.projects p ON p.id = s.project_id
LEFT JOIN clean_jira.issues i ON i.id = si.issue_id
LEFT JOIN clean_jira.issue_types it ON it.id = i.type_id
WHERE s.name = 'ADS Спринт 15'
GROUP BY si.sprint_id, p.external_key, p.name
ORDER BY p.external_key;

-- 4. Детальная информация о задачах в спринте
SELECT
    s.id as sprint_id,
    p.external_key as project_key,
    s.name as sprint_name,
    i.external_key as issue_key,
    i.project_id as issue_project_id,
    ip.external_key as issue_project_key,
    it.name as issue_type,
    i.jira_created_at,
    i.jira_resolved_at
FROM clean_jira.sprint_issues si
INNER JOIN clean_jira.sprints s ON s.id = si.sprint_id
INNER JOIN clean_jira.projects p ON p.id = s.project_id
LEFT JOIN clean_jira.issues i ON i.id = si.issue_id
LEFT JOIN clean_jira.projects ip ON ip.id = i.project_id
LEFT JOIN clean_jira.issue_types it ON it.id = i.type_id
WHERE s.name = 'ADS Спринт 15'
ORDER BY p.external_key, i.external_key;

-- 5. Проверяем RAW таблицы - может проблема в источнике данных
SELECT
    id,
    project_id,
    name,
    state,
    start_date,
    end_date,
    complete_date,
    _dlt_load_id,
    _dlt_id
FROM raw_jira_twad.sprints
WHERE name = 'ADS Спринт 15';

SELECT
    id,
    project_id,
    name,
    state,
    start_date,
    end_date,
    complete_date,
    _dlt_load_id,
    _dlt_id
FROM raw_jira_twmob.sprints
WHERE name = 'ADS Спринт 15';

-- 6. Проверяем все спринты с одинаковым именем (может есть и другие дубликаты)
SELECT
    s.name as sprint_name,
    COUNT(DISTINCT s.id) as sprint_records,
    COUNT(DISTINCT s.project_id) as projects_count,
    STRING_AGG(DISTINCT p.external_key, ', ') as project_keys,
    STRING_AGG(DISTINCT p.name, ', ') as project_names
FROM clean_jira.sprints s
LEFT JOIN clean_jira.projects p ON p.id = s.project_id
GROUP BY s.name
HAVING COUNT(DISTINCT s.project_id) > 1
ORDER BY sprint_name;

-- 7. Проверяем Story Points для задач этого спринта
SELECT
    s.id as sprint_id,
    p.external_key as project_key,
    i.external_key as issue_key,
    fk.external_key as field_key,
    fk.name as field_name,
    fv.json_value as story_points_value
FROM clean_jira.sprint_issues si
INNER JOIN clean_jira.sprints s ON s.id = si.sprint_id
INNER JOIN clean_jira.projects p ON p.id = s.project_id
LEFT JOIN clean_jira.issues i ON i.id = si.issue_id
LEFT JOIN clean_jira.field_values fv ON fv.issue_id = i.id
LEFT JOIN clean_jira.field_keys fk ON fk.id = fv.field_key_id
WHERE s.name = 'ADS Спринт 15'
  AND (fk.external_key IN ('customfield_10036', 'story_points')
       OR fk.name ILIKE '%story point%')
ORDER BY p.external_key, i.external_key;
