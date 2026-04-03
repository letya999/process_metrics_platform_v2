-- Flow Efficiency status mapping by project/board columns.
-- Generated from agreed active/passive column classification (On review -> active).

WITH calc_ids AS (
  SELECT id AS calc_id
  FROM metrics.calculations
  WHERE calc_code IN ('flow_active_days', 'flow_wait_days', 'flow_efficiency_pct')
),
column_rules AS (
  SELECT *
  FROM (
    VALUES
      ('TWAD','In progress','active'),('TWAD','On review','active'),('TWAD','Testing','active'),
      ('TWAD','To do','passive'),('TWAD','Ready for QA','passive'),('TWAD','Wait for release','passive'),
      ('TWAQA','In Progress','active'),('TWAQA','Review','active'),
      ('TWAQA','To Do','passive'),
      ('TWBACKEND','In Progress','active'),('TWBACKEND','On review','active'),('TWBACKEND','Testing','active'),
      ('TWBACKEND','To Do','passive'),('TWBACKEND','ON HOLD','passive'),('TWBACKEND','After test','passive'),
      ('TWBACKEND','Ready for qa','passive'),('TWBACKEND','Wait for release','passive'),
      ('TWCE','To Do','active'),('TWCE','In Progress','active'),('TWCE','Design Review','active'),
      ('TWCE','Взять в работу','active'),('TWCE','ресерч','active'),('TWCE','Прописать бизнес-требования','active'),
      ('TWCE','Проектирование архитектуры','active'),('TWCE','Дизайн','active'),('TWCE','Дизайн ревью','active'),('TWCE','Разработка','active'),
      ('TWCE','Backlog','passive'),('TWCE','Hold','passive'),('TWCE','Бэклог','passive'),('TWCE','Холд','passive'),
      ('TWCE','Системные аналитики + ТА от QA','passive'),('TWCE','Приемка ТА','passive'),('TWCE','Приемка фичи и релиз','passive'),('TWCE','Оценка фичи','passive'),
      ('TWMOB','In Progress','active'),('TWMOB','on review','active'),('TWMOB','Testing','active'),
      ('TWMOB','To Do','passive'),('TWMOB','After test','passive'),('TWMOB','on hold','passive'),('TWMOB','not uploaded','passive'),('TWMOB','ready for qa','passive'),
      ('TWSA','In Progress','active'),('TWSA','SA Review','active'),
      ('TWSA','To Do','passive'),('TWSA','APPROVE DEV','passive'),('TWSA','APPROVE QA','passive'),
      ('TWSC','In Progress','active'),('TWSC','Review','active'),
      ('TWSC','To Do','passive'),
      ('TWSUP','В тестировании','active'),
      ('TWSUP','К выполнению','passive'),('TWSUP','Плавающий баг','passive'),('TWSUP','Нехватка данных','passive'),('TWSUP','Передано в разработку','passive'),
      ('TWWB','In Progress','active'),('TWWB','on review','active'),('TWWB','testing','active'),
      ('TWWB','To Do','passive'),('TWWB','on hold','passive'),('TWWB','Needs refinement','passive'),('TWWB','ready for qa','passive'),('TWWB','Ready to be merged','passive'),('TWWB','Wait for release','passive')
  ) AS t(project_key, column_name, bucket)
),
projects AS (
  SELECT id AS project_id, external_key AS project_key
  FROM clean_jira.projects
  WHERE external_key IN ('TWAD','TWAQA','TWBACKEND','TWCE','TWMOB','TWSA','TWSC','TWSUP','TWWB')
),
status_by_rule AS (
  SELECT p.project_id,
         p.project_key,
         r.bucket,
         s.id AS status_id
  FROM column_rules r
  JOIN projects p ON p.project_key = r.project_key
  JOIN clean_jira.boards b ON b.project_id = p.project_id
  JOIN clean_jira.board_columns bc ON bc.board_id = b.id AND bc.name = r.column_name
  JOIN clean_jira.board_column_statuses bcs ON bcs.board_column_id = bc.id
  JOIN clean_jira.issue_statuses s ON s.id = bcs.status_id
),
agg AS (
  SELECT p.project_id,
         p.project_key,
         array_remove(array_agg(DISTINCT sbr.status_id) FILTER (WHERE sbr.bucket='active'), NULL) AS active_status_ids_raw,
         array_remove(array_agg(DISTINCT sbr.status_id) FILTER (WHERE sbr.bucket='passive'), NULL) AS passive_status_ids_raw,
         array_remove(array_agg(DISTINCT s.id) FILTER (WHERE s.category='done'), NULL) AS done_status_ids
  FROM projects p
  LEFT JOIN status_by_rule sbr ON sbr.project_id = p.project_id
  LEFT JOIN clean_jira.issue_statuses s ON s.project_id = p.project_id
  GROUP BY p.project_id, p.project_key
),
normalized AS (
  SELECT
    project_id,
    project_key,
    COALESCE(active_status_ids_raw, ARRAY[]::uuid[]) AS active_status_ids,
    ARRAY(
      SELECT x
      FROM unnest(COALESCE(passive_status_ids_raw, ARRAY[]::uuid[])) x
      WHERE x <> ALL(COALESCE(active_status_ids_raw, ARRAY[]::uuid[]))
    ) AS passive_status_ids,
    COALESCE(done_status_ids, ARRAY[]::uuid[]) AS done_status_ids
  FROM agg
),
payload AS (
  SELECT
    n.project_id,
    c.calc_id AS target_calculation_id,
    'flow_status_categories'::text AS settings_type,
    jsonb_build_object(
      'mode', 'status_ids',
      'active_status_ids', to_jsonb(n.active_status_ids),
      'passive_status_ids', to_jsonb(n.passive_status_ids),
      'done_status_ids', to_jsonb(n.done_status_ids),
      'active_categories', jsonb_build_array('in_progress'),
      'passive_categories', jsonb_build_array('to_do'),
      'done_categories', jsonb_build_array('done')
    ) AS settings_json,
    TRUE AS enabled
  FROM normalized n
  CROSS JOIN calc_ids c
)
INSERT INTO metrics.calculation_settings (
  project_id,
  target_calculation_id,
  settings_type,
  settings_json,
  enabled
)
SELECT project_id, target_calculation_id, settings_type, settings_json, enabled
FROM payload
ON CONFLICT (project_id, target_calculation_id, settings_type)
DO UPDATE SET
  settings_json = EXCLUDED.settings_json,
  enabled = EXCLUDED.enabled,
  updated_at = now();
