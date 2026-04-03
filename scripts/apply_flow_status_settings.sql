BEGIN;

CREATE TEMP TABLE tmp_flow_payload ON COMMIT DROP AS
WITH calc_ids AS (
  SELECT DISTINCT id AS calc_id
  FROM metrics.calculations
  WHERE calc_code IN ('flow_active_days', 'flow_wait_days', 'flow_efficiency_pct')
),
column_rules AS (
  SELECT *
  FROM (
    VALUES
      ('TWAD','6e7247b2-71b3-4c85-b5da-2656932e0c84','active'),
      ('TWAD','30f992b3-13cd-45f1-92f3-d350ae831681','active'),
      ('TWAD','6cb5f7ed-8eb6-4359-802d-2153b218ea34','active'),
      ('TWAD','a8bbe9ec-a8dc-4a0d-ae3d-e9a202c7d6ae','passive'),
      ('TWAD','15fbf959-46a2-4d33-8c72-3122a0c42257','passive'),
      ('TWAD','b2a6057b-5d5b-49ac-b322-12a94a3e699b','passive'),
      ('TWAQA','51b27d4f-5c5b-4835-97b7-abc8a787e9ea','active'),
      ('TWAQA','71fa300b-a051-4415-95fc-484108838b4b','active'),
      ('TWAQA','5c371110-a138-460b-bf07-0088e23a2843','passive'),
      ('TWBACKEND','ad32eb17-b4d6-4214-a176-0803d58c4adb','active'),
      ('TWBACKEND','591f8859-e3f2-43b1-90ff-6edab7499c73','active'),
      ('TWBACKEND','dcfa4432-007c-4472-8103-5fa302548f37','active'),
      ('TWBACKEND','a9b6c2a5-cd14-4de5-94e2-0504737b8ab1','passive'),
      ('TWBACKEND','3b8aa36a-b1c0-497a-a561-2d40ea9a7d02','passive'),
      ('TWBACKEND','ac251bb1-ad2a-4748-9036-19fdcf98cd6e','passive'),
      ('TWBACKEND','7b376578-6ec4-48d3-b951-3581b7ac1b5d','passive'),
      ('TWBACKEND','fea059a0-c39e-41b3-9668-96bd27e0e7db','passive'),
      ('TWCE','dff8d663-8797-43da-a2e8-59239c0fd726','active'),
      ('TWCE','698e7f43-6344-4a67-9a17-508343eaafa5','active'),
      ('TWCE','36fbdd16-e049-4f64-8874-ec0e02893dca','active'),
      ('TWCE','7f665ce8-8a44-4906-a717-1fb174b90637','passive'),
      ('TWCE','4759c8c4-1a75-4ccb-b0ee-ecf4d522f4c5','passive'),
      ('TWCE','b873004e-22dc-4d61-a74b-f95da3f3a25b','active'),
      ('TWCE','0bd7d304-bb69-4986-b51d-59ab46795694','active'),
      ('TWCE','719be1b8-c545-42cd-9c75-475bfb7ea19c','active'),
      ('TWCE','0b4e8167-4605-438e-9a9e-22b8315dd0c8','active'),
      ('TWCE','0e1b7193-c91b-4657-9d2f-a71b10252608','active'),
      ('TWCE','9aa73e14-1eea-47ba-9313-12b5df688957','active'),
      ('TWCE','a3805d01-1784-46ea-a284-05cc1504d94f','active'),
      ('TWCE','d08636ce-cb54-4ad2-8dd3-9075cbe4fc06','passive'),
      ('TWCE','57e52b45-0b06-4fa6-b823-5671d89682cc','passive'),
      ('TWCE','0b4dc89a-7e2a-421f-b445-9789b44686da','passive'),
      ('TWCE','66663b35-8442-4e32-a0cd-ef189f2f9816','passive'),
      ('TWCE','a03a8184-bf29-456d-91eb-f6b8fe4454c0','passive'),
      ('TWCE','4f4e0949-d1e3-483b-91f8-0b29200deab2','passive'),
      ('TWCE','0b156dd9-f584-4cb6-b30b-76123ee5c054','passive'),
      ('TWMOB','105afe28-f151-4799-8000-5773a972d6f5','active'),
      ('TWMOB','65fd55e0-f5fe-4e7c-a0d0-53be48aa8b12','active'),
      ('TWMOB','b06300d5-a094-4fb1-be0d-774ac7e61e97','active'),
      ('TWMOB','c1b82cbe-1095-4bc0-af64-1ad8c7f1e1dc','passive'),
      ('TWMOB','1c832a0a-1efd-45d3-8fa0-55bc65748f30','passive'),
      ('TWMOB','2e847126-ea9b-4aad-b7a0-82086675147c','passive'),
      ('TWMOB','2f4c83eb-c8d3-4de8-b7e5-d04e0d968bc1','passive'),
      ('TWMOB','54a74a9d-e184-4b25-9f22-2ba240eb2e51','passive'),
      ('TWSA','dd329830-f081-4a60-ba2b-b21224a9e457','active'),
      ('TWSA','cf235b41-2c00-4706-a6ef-50ddfdc7b495','active'),
      ('TWSA','9ffd79c3-51e0-4f5e-9edd-548324167de0','passive'),
      ('TWSA','054e4d1c-0210-41ce-a989-efb43553f2d5','passive'),
      ('TWSA','a6ee72fb-c665-4abb-87cb-9ba4d1b17051','passive'),
      ('TWSC','c8f8945c-757e-471a-bd74-6f336e8572e8','active'),
      ('TWSC','e48ba4c8-c500-40ac-8e34-764ba12bc40a','active'),
      ('TWSC','9cf2e9ad-374d-432f-9691-995ad820d934','passive'),
      ('TWSUP','0e717d15-afec-4bc5-9d2f-b73e45316ee8','active'),
      ('TWSUP','d4431586-957d-40a8-85a4-25a80031d350','passive'),
      ('TWSUP','ec1def42-bbaa-4fcc-b81c-0a2cc7c073f9','passive'),
      ('TWSUP','8aee9f26-21e8-4e21-ab13-cd8c40b4401d','passive'),
      ('TWSUP','fbb8bdac-c888-4ba8-ad0e-5cd654ea8da7','passive'),
      ('TWWB','3005b434-b115-4c03-a333-4fc49f510ae3','active'),
      ('TWWB','77417ae2-f90b-47bf-9aed-5f3fcbe64d5a','active'),
      ('TWWB','7fa99a6e-ce5d-49f7-a5f5-05cee9e0fa62','active'),
      ('TWWB','5cd08696-c082-46cc-bc99-40247350898a','passive'),
      ('TWWB','700981ed-4aa6-4989-be76-a376228e76e8','passive'),
      ('TWWB','cc4cde61-b8f0-4788-9be1-26be2b4722e2','passive'),
      ('TWWB','68236ef8-a497-4d28-b08c-b90c14decfa1','passive'),
      ('TWWB','2e6ba36b-7265-4f1e-8c3c-1e9aa1a2bdb5','passive'),
      ('TWWB','9c4e9456-e18c-486b-bd24-87899fa9d578','passive')
  ) AS t(project_key, column_id, bucket)
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
  JOIN clean_jira.board_columns bc ON bc.board_id = b.id AND bc.id::text = r.column_id
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
    COALESCE(active_status_ids_raw, ARRAY[]::uuid[]) AS active_status_ids,
    ARRAY(
      SELECT x
      FROM unnest(COALESCE(passive_status_ids_raw, ARRAY[]::uuid[])) x
      WHERE x <> ALL(COALESCE(active_status_ids_raw, ARRAY[]::uuid[]))
    ) AS passive_status_ids,
    COALESCE(done_status_ids, ARRAY[]::uuid[]) AS done_status_ids
  FROM agg
)
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
CROSS JOIN calc_ids c;

DELETE FROM metrics.calculation_settings cs
USING tmp_flow_payload p
WHERE cs.project_id = p.project_id
  AND cs.target_calculation_id = p.target_calculation_id
  AND cs.settings_type = p.settings_type;

INSERT INTO metrics.calculation_settings (
  project_id,
  target_calculation_id,
  settings_type,
  settings_json,
  enabled
)
SELECT project_id, target_calculation_id, settings_type, settings_json, enabled
FROM tmp_flow_payload;

COMMIT;
