import logging
from datetime import datetime, timedelta
from typing import List, Tuple

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook


# @anchor:dag:metrics_velocity:get_projects
def get_projects(**kwargs) -> List[Tuple[str, str]]:
    """Возвращает список проектов для перерасчета velocity.

    Фильтр по `project_keys` из dagrun.conf (список строк) поддерживается.
    Возвращает список пар (project_id, project_key)
    """
    pg = PostgresHook(postgres_conn_id="postgres_default")
    conf = (kwargs.get("dag_run") or {}).conf or {}
    filter_keys = conf.get("project_keys") if isinstance(conf, dict) else None
    user_id = conf.get("user_id") if isinstance(conf, dict) else None
    integration_uuid = conf.get("integration_uuid") if isinstance(conf, dict) else None
    if filter_keys and not isinstance(filter_keys, list):
        filter_keys = [filter_keys]

    base_sql = """
        SELECT id::text, external_key
        FROM projects
        WHERE 1=1
    """
    params: List = []
    if filter_keys:
        logging.info(f"Filtering projects by keys: {filter_keys}")
        placeholders = ",".join(["%s"] * len(filter_keys))
        # поддержка UUID id
        if all(isinstance(k, str) and len(k) == 36 and "-" in k for k in filter_keys):
            base_sql += f" AND id IN ({placeholders})"
        else:
            base_sql += f" AND external_key IN ({placeholders})"
        params.extend(filter_keys)
    if user_id:
        base_sql += " AND user_id = %s::uuid"
        params.append(user_id)
    if integration_uuid:
        base_sql += " AND tool_integration_id = %s::uuid"
        params.append(integration_uuid)
    base_sql += " ORDER BY external_key"
    rows = pg.get_records(base_sql, parameters=tuple(params) if params else None)

    if not rows:
        logging.warning("No projects found for metrics velocity recalculation")
    else:
        logging.info(f"Selected {len(rows)} projects: {[r[1] for r in rows]}")

    kwargs["ti"].xcom_push(key="projects", value=rows)
    return rows


# @anchor:dag:metrics_velocity:sql
DELETE_SQL = """
DELETE FROM fact_velocity
WHERE project_id = %s::uuid;
"""

INSERT_SQL = """
BEGIN;

WITH params AS (
  SELECT %s::uuid AS project_id
),

-- DONE-статусы (commitment_end)
end_statuses AS (
  SELECT DISTINCT s.id AS status_id
  FROM board_commitment_points cp
  JOIN board_columns bc          ON bc.id = cp.board_column_id
  JOIN board_column_statuses bcs ON bcs.board_column_id = bc.id
  JOIN statuses s                ON s.id = bcs.status_id
  JOIN boards b                  ON b.id = bc.board_id
  JOIN params p                  ON p.project_id = b.project_id
  WHERE cp.role = 'commitment_end'
),

-- все итерации
iters AS (
  SELECT it.*
  FROM iterations it
  JOIN params p ON p.project_id = it.project_id
  WHERE it.start_date IS NOT NULL
    AND it.end_date   IS NOT NULL
),

-- все задачи в итерациях
issues_in_sprint AS (
  SELECT DISTINCT i.id, i.estimate, ii.iteration_id, i.current_status_id, i.resolved
  FROM issues i
  JOIN issue_iterations ii ON ii.issue_id = i.id
  JOIN iters it ON it.id = ii.iteration_id
  JOIN params p ON p.project_id = i.project_id
),

-- переходы в Done до окончания спринта
done_by_history AS (
  SELECT
    i.id AS issue_id,
    ii.iteration_id,
    MIN(h.changed_at) AS completion_ts
  FROM issues i
  JOIN issue_status_history h ON h.issue_id = i.id
  JOIN end_statuses es        ON es.status_id = h.to_status_id
  JOIN issue_iterations ii    ON ii.issue_id = i.id
  JOIN iters it               ON it.id = ii.iteration_id
  WHERE h.changed_at::date <= it.end_date
  GROUP BY i.id, ii.iteration_id
),

-- задачи в Done по текущему статусу
done_by_current AS (
  SELECT isp.id AS issue_id, isp.iteration_id
  FROM issues_in_sprint isp
  JOIN end_statuses es ON es.status_id = isp.current_status_id
),

-- fallback через resolution_date
done_by_resolution AS (
  SELECT isp.id AS issue_id, isp.iteration_id
  FROM issues_in_sprint isp
  JOIN iters it ON it.id = isp.iteration_id
  WHERE isp.resolved IS NOT NULL
    AND isp.resolved::date <= it.end_date
),

-- финальное объединение
done_union AS (
  -- прошлые спринты
  SELECT dh.issue_id, dh.iteration_id
  FROM done_by_history dh
  JOIN iters it ON it.id = dh.iteration_id
  WHERE it.end_date < CURRENT_DATE

  UNION
  SELECT dr.issue_id, dr.iteration_id
  FROM done_by_resolution dr
  JOIN iters it ON it.id = dr.iteration_id
  WHERE it.end_date < CURRENT_DATE

  -- активный спринт
  UNION
  SELECT dh.issue_id, dh.iteration_id
  FROM done_by_history dh
  JOIN iters it ON it.id = dh.iteration_id
  WHERE it.start_date <= CURRENT_DATE
    AND it.end_date   >= CURRENT_DATE

  UNION
  SELECT dc.issue_id, dc.iteration_id
  FROM done_by_current dc
  JOIN iters it ON it.id = dc.iteration_id
  WHERE it.start_date <= CURRENT_DATE
    AND it.end_date   >= CURRENT_DATE

  UNION
  SELECT dr.issue_id, dr.iteration_id
  FROM done_by_resolution dr
  JOIN iters it ON it.id = dr.iteration_id
  WHERE it.start_date <= CURRENT_DATE
    AND it.end_date   >= CURRENT_DATE
)

-- вставка в fact_velocity
INSERT INTO fact_velocity (
    id,
    project_id,
    iteration_id,
    iteration_name,
    start_date,
    end_date,
    issue_type,
    custom_field_value,
    planned_story_points,
    completed_story_points,
    planned_issues,
    completed_issues
)
SELECT
  gen_random_uuid(),
  (SELECT project_id FROM params)              AS project_id,
  it.id                                        AS iteration_id,
  it.name                                      AS iteration_name,
  it.start_date,
  it.end_date,
  NULL::text                                   AS issue_type,
  NULL::text                                   AS custom_field_value,
  COALESCE(SUM(isp.estimate),0)                AS planned_story_points,
  COALESCE(SUM(CASE WHEN du.issue_id IS NOT NULL THEN isp.estimate ELSE 0 END),0) AS completed_story_points,
  COUNT(DISTINCT isp.id)                       AS planned_issues,
  COUNT(DISTINCT du.issue_id)                  AS completed_issues
FROM iters it
LEFT JOIN issues_in_sprint isp ON isp.iteration_id = it.id
LEFT JOIN done_union du        ON du.issue_id = isp.id AND du.iteration_id = it.id
GROUP BY it.id, it.name, it.start_date, it.end_date
ORDER BY it.start_date, it.name;

COMMIT;
"""


# Server-side variant that reads project_id from temp table tmp_current_project
# to avoid client-side percent formatting issues in multi-statement SQL.
INSERT_SQL_V2_FROM_TMP = """
WITH params AS (
  SELECT (SELECT project_id FROM tmp_current_project) AS project_id
),
iters AS (
  SELECT it.*
  FROM iterations it
  JOIN params p ON p.project_id = it.project_id
  WHERE it.start_date IS NOT NULL AND it.end_date IS NOT NULL
),
end_statuses AS (
  SELECT DISTINCT s.id AS status_id
  FROM board_commitment_points cp
  JOIN board_columns bc          ON bc.id = cp.board_column_id
  JOIN board_column_statuses bcs ON bcs.board_column_id = bc.id
  JOIN statuses s                ON s.id = bcs.status_id
  JOIN boards b                  ON b.id = bc.board_id
  JOIN params p                  ON p.project_id = b.project_id
  WHERE cp.role = 'commitment_end'
),
membership_base AS (
  SELECT DISTINCT ii.issue_id, ii.iteration_id
  FROM issue_iterations ii
  JOIN iters it ON it.id = ii.iteration_id
),
state_at_start AS (
  SELECT m.issue_id, m.iteration_id,
         (
           SELECT h.action
           FROM issue_iteration_history h
           JOIN iters it2 ON it2.id = h.iteration_id
           WHERE h.issue_id = m.issue_id
             AND h.iteration_id = m.iteration_id
             AND h.changed_at <= (it2.start_date::timestamptz + interval '23:59:59')
           ORDER BY h.changed_at DESC
           LIMIT 1
         ) AS action_at_start
  FROM membership_base m
),
planned_pairs AS (
  SELECT s.issue_id, s.iteration_id
  FROM state_at_start s
  JOIN iters it ON it.id = s.iteration_id
  JOIN issues i ON i.id = s.issue_id
  WHERE (s.action_at_start = 'added')
     OR (s.action_at_start IS NULL AND i.created::date <= it.start_date)
),
sp_fields AS (
  SELECT id AS custom_field_id
  FROM custom_fields
  WHERE project_id = (SELECT project_id FROM params)
    AND (
      external_key IN ('customfield_10036','customfield_10016','story_points')
      OR LOWER(name) LIKE '%story point%'
    )
),
planned_sp AS (
  SELECT p.issue_id, p.iteration_id,
         COALESCE(
           (
             SELECT CASE
                      WHEN jsonb_typeof(ch.new_value) = 'object' AND ch.new_value ? 'value' THEN NULLIF(ch.new_value->>'value','')::numeric
                      WHEN jsonb_typeof(ch.new_value) = 'number' THEN (ch.new_value)::numeric
                      WHEN jsonb_typeof(ch.new_value) = 'string' THEN NULLIF(trim(both '"' from ch.new_value::text),'')::numeric
                      ELSE NULL
                    END
             FROM custom_field_history ch
             JOIN iters it ON it.id = p.iteration_id
             WHERE ch.issue_id = p.issue_id
               AND ch.custom_field_id IN (SELECT custom_field_id FROM sp_fields)
               AND ch.changed_at <= (it.start_date)::timestamptz + interval '23:59:59'
             ORDER BY ch.changed_at DESC
             LIMIT 1
           ),
           (
             SELECT CASE
                      WHEN jsonb_typeof(cfv.value) = 'object' AND cfv.value ? 'value' THEN NULLIF(cfv.value->>'value','')::numeric
                      WHEN jsonb_typeof(cfv.value) = 'number' THEN (cfv.value)::numeric
                      WHEN jsonb_typeof(cfv.value) = 'string' THEN NULLIF(trim(both '"' from cfv.value::text),'')::numeric
                      ELSE NULL
                    END
             FROM custom_field_values cfv
             JOIN custom_fields cf ON cf.id = cfv.custom_field_id
             WHERE cf.project_id = (SELECT project_id FROM params)
               AND cf.id IN (SELECT custom_field_id FROM sp_fields)
               AND cfv.issue_id = p.issue_id
             LIMIT 1
           ),
           (SELECT i.estimate::numeric FROM issues i WHERE i.id = p.issue_id)
         ) AS story_points
  FROM planned_pairs p
),
done_by_history AS (
  SELECT p.issue_id, p.iteration_id, MIN(h.changed_at) AS completion_ts
  FROM planned_pairs p
  JOIN issue_status_history h ON h.issue_id = p.issue_id
  JOIN end_statuses es ON es.status_id = h.to_status_id
  JOIN iters it ON it.id = p.iteration_id
  WHERE h.changed_at::date <= it.end_date
  GROUP BY p.issue_id, p.iteration_id
),
done_by_resolution AS (
  SELECT p.issue_id, p.iteration_id
  FROM planned_pairs p
  JOIN issues i ON i.id = p.issue_id
  JOIN iters it ON it.id = p.iteration_id
  WHERE i.resolved IS NOT NULL AND i.resolved::date <= it.end_date
),
done_by_current AS (
  SELECT p.issue_id, p.iteration_id
  FROM planned_pairs p
  JOIN issues i ON i.id = p.issue_id
  JOIN end_statuses es ON es.status_id = i.current_status_id
  JOIN iters it ON it.id = p.iteration_id
  WHERE it.start_date <= CURRENT_DATE AND it.end_date >= CURRENT_DATE
),
done_union AS (
  SELECT dh.issue_id, dh.iteration_id FROM done_by_history dh JOIN iters it ON it.id = dh.iteration_id WHERE it.end_date < CURRENT_DATE
  UNION SELECT dr.issue_id, dr.iteration_id FROM done_by_resolution dr JOIN iters it ON it.id = dr.iteration_id WHERE it.end_date < CURRENT_DATE
  UNION SELECT dh.issue_id, dh.iteration_id FROM done_by_history dh JOIN iters it ON it.id = dh.iteration_id WHERE it.start_date <= CURRENT_DATE AND it.end_date >= CURRENT_DATE
  UNION SELECT dc.issue_id, dc.iteration_id FROM done_by_current dc JOIN iters it ON it.id = dc.iteration_id WHERE it.start_date <= CURRENT_DATE AND it.end_date >= CURRENT_DATE
  UNION SELECT dr.issue_id, dr.iteration_id FROM done_by_resolution dr JOIN iters it ON it.id = dr.iteration_id WHERE it.start_date <= CURRENT_DATE AND it.end_date >= CURRENT_DATE
),
planned_agg AS (
  SELECT p.iteration_id,
         COUNT(DISTINCT p.issue_id) AS planned_issues,
         COALESCE(SUM(COALESCE(ps.story_points,0)),0) AS planned_story_points
  FROM planned_pairs p
  LEFT JOIN planned_sp ps ON ps.issue_id = p.issue_id AND ps.iteration_id = p.iteration_id
  GROUP BY p.iteration_id
),
completed_agg AS (
  SELECT p.iteration_id,
         COUNT(DISTINCT du.issue_id) AS completed_issues,
         COALESCE(SUM(COALESCE(ps.story_points,0)),0) AS completed_story_points
  FROM planned_pairs p
  JOIN done_union du ON du.issue_id = p.issue_id AND du.iteration_id = p.iteration_id
  LEFT JOIN planned_sp ps ON ps.issue_id = p.issue_id AND ps.iteration_id = p.iteration_id
  GROUP BY p.iteration_id
)
INSERT INTO fact_velocity (
    id,
    project_id,
    iteration_id,
    iteration_name,
    start_date,
    end_date,
    issue_type,
    custom_field_value,
    planned_story_points,
    completed_story_points,
    planned_issues,
    completed_issues
)
SELECT
  gen_random_uuid(),
  (SELECT project_id FROM params) AS project_id,
  it.id                           AS iteration_id,
  it.name                         AS iteration_name,
  it.start_date,
  it.end_date,
  NULL::text                      AS issue_type,
  NULL::text                      AS custom_field_value,
  COALESCE(pa.planned_story_points,0)   AS planned_story_points,
  COALESCE(ca.completed_story_points,0) AS completed_story_points,
  COALESCE(pa.planned_issues,0)         AS planned_issues,
  COALESCE(ca.completed_issues,0)       AS completed_issues
FROM iters it
LEFT JOIN planned_agg pa   ON pa.iteration_id = it.id
LEFT JOIN completed_agg ca ON ca.iteration_id = it.id
ORDER BY it.start_date, it.name;
"""


# Improved SQL: plan at sprint start from history; complete within window; sum SP at start
INSERT_SQL_V2 = """
BEGIN;

WITH params AS (
  SELECT %s::uuid AS project_id
),

iters AS (
  SELECT it.*
  FROM iterations it
  JOIN params p ON p.project_id = it.project_id
  WHERE it.start_date IS NOT NULL AND it.end_date IS NOT NULL
),

-- commitment end statuses
end_statuses AS (
  SELECT DISTINCT s.id AS status_id
  FROM board_commitment_points cp
  JOIN board_columns bc          ON bc.id = cp.board_column_id
  JOIN board_column_statuses bcs ON bcs.board_column_id = bc.id
  JOIN statuses s                ON s.id = bcs.status_id
  JOIN boards b                  ON b.id = bc.board_id
  JOIN params p                  ON p.project_id = b.project_id
  WHERE cp.role = 'commitment_end'
),

-- base pairs per iteration
membership_base AS (
  SELECT DISTINCT ii.issue_id, ii.iteration_id
  FROM issue_iterations ii
  JOIN iters it ON it.id = ii.iteration_id
),

-- last membership action at or before sprint start
state_at_start AS (
  SELECT m.issue_id, m.iteration_id,
         (
           SELECT h.action
           FROM issue_iteration_history h
           JOIN iters it2 ON it2.id = h.iteration_id
           WHERE h.issue_id = m.issue_id
             AND h.iteration_id = m.iteration_id
             AND h.changed_at <= (it2.start_date::timestamptz + interval '23:59:59')
           ORDER BY h.changed_at DESC
           LIMIT 1
         ) AS action_at_start
  FROM membership_base m
),

planned_pairs AS (
  SELECT s.issue_id, s.iteration_id
  FROM state_at_start s
  JOIN iters it ON it.id = s.iteration_id
  JOIN issues i ON i.id = s.issue_id
  WHERE (s.action_at_start = 'added')
     OR (s.action_at_start IS NULL AND i.created::date <= it.start_date)
),

sp_fields AS (
  SELECT id AS custom_field_id
  FROM custom_fields
  WHERE project_id = (SELECT project_id FROM params)
    AND (
      external_key IN ('customfield_10036','customfield_10016','story_points')
      OR LOWER(name) LIKE '%story point%'
    )
),

planned_sp AS (
  SELECT p.issue_id, p.iteration_id,
         COALESCE(
           (
             SELECT CASE
                      WHEN jsonb_typeof(ch.new_value) = 'object' AND ch.new_value ? 'value' THEN NULLIF(ch.new_value->>'value','')::numeric
                      WHEN jsonb_typeof(ch.new_value) = 'number' THEN (ch.new_value)::numeric
                      WHEN jsonb_typeof(ch.new_value) = 'string' THEN NULLIF(trim(both '"' from ch.new_value::text),'')::numeric
                      ELSE NULL
                    END
             FROM custom_field_history ch
             JOIN iters it ON it.id = p.iteration_id
             WHERE ch.issue_id = p.issue_id
               AND ch.custom_field_id IN (SELECT custom_field_id FROM sp_fields)
               AND ch.changed_at <= (it.start_date)::timestamptz + interval '23:59:59'
             ORDER BY ch.changed_at DESC
             LIMIT 1
           ),
           (
             SELECT CASE
                      WHEN jsonb_typeof(cfv.value) = 'object' AND cfv.value ? 'value' THEN NULLIF(cfv.value->>'value','')::numeric
                      WHEN jsonb_typeof(cfv.value) = 'number' THEN (cfv.value)::numeric
                      WHEN jsonb_typeof(cfv.value) = 'string' THEN NULLIF(trim(both '"' from cfv.value::text),'')::numeric
                      ELSE NULL
                    END
             FROM custom_field_values cfv
             JOIN custom_fields cf ON cf.id = cfv.custom_field_id
             WHERE cf.project_id = (SELECT project_id FROM params)
               AND cf.id IN (SELECT custom_field_id FROM sp_fields)
               AND cfv.issue_id = p.issue_id
             LIMIT 1
           ),
           (SELECT i.estimate::numeric FROM issues i WHERE i.id = p.issue_id)
         ) AS story_points
  FROM planned_pairs p
),

done_by_history AS (
  SELECT p.issue_id, p.iteration_id, MIN(h.changed_at) AS completion_ts
  FROM planned_pairs p
  JOIN issue_status_history h ON h.issue_id = p.issue_id
  JOIN end_statuses es ON es.status_id = h.to_status_id
  JOIN iters it ON it.id = p.iteration_id
  WHERE h.changed_at::date <= it.end_date
  GROUP BY p.issue_id, p.iteration_id
),

done_by_resolution AS (
  SELECT p.issue_id, p.iteration_id
  FROM planned_pairs p
  JOIN issues i ON i.id = p.issue_id
  JOIN iters it ON it.id = p.iteration_id
  WHERE i.resolved IS NOT NULL AND i.resolved::date <= it.end_date
),

done_by_current AS (
  SELECT p.issue_id, p.iteration_id
  FROM planned_pairs p
  JOIN issues i ON i.id = p.issue_id
  JOIN end_statuses es ON es.status_id = i.current_status_id
  JOIN iters it ON it.id = p.iteration_id
  WHERE it.start_date <= CURRENT_DATE AND it.end_date >= CURRENT_DATE
),

done_union AS (
  SELECT dh.issue_id, dh.iteration_id FROM done_by_history dh JOIN iters it ON it.id = dh.iteration_id WHERE it.end_date < CURRENT_DATE
  UNION SELECT dr.issue_id, dr.iteration_id FROM done_by_resolution dr JOIN iters it ON it.id = dr.iteration_id WHERE it.end_date < CURRENT_DATE
  UNION SELECT dh.issue_id, dh.iteration_id FROM done_by_history dh JOIN iters it ON it.id = dh.iteration_id WHERE it.start_date <= CURRENT_DATE AND it.end_date >= CURRENT_DATE
  UNION SELECT dc.issue_id, dc.iteration_id FROM done_by_current dc JOIN iters it ON it.id = dc.iteration_id WHERE it.start_date <= CURRENT_DATE AND it.end_date >= CURRENT_DATE
  UNION SELECT dr.issue_id, dr.iteration_id FROM done_by_resolution dr JOIN iters it ON it.id = dr.iteration_id WHERE it.start_date <= CURRENT_DATE AND it.end_date >= CURRENT_DATE
),

planned_agg AS (
  SELECT p.iteration_id,
         COUNT(DISTINCT p.issue_id) AS planned_issues,
         COALESCE(SUM(COALESCE(ps.story_points,0)),0) AS planned_story_points
  FROM planned_pairs p
  LEFT JOIN planned_sp ps ON ps.issue_id = p.issue_id AND ps.iteration_id = p.iteration_id
  GROUP BY p.iteration_id
),

completed_agg AS (
  SELECT p.iteration_id,
         COUNT(DISTINCT du.issue_id) AS completed_issues,
         COALESCE(SUM(COALESCE(ps.story_points,0)),0) AS completed_story_points
  FROM planned_pairs p
  JOIN done_union du ON du.issue_id = p.issue_id AND du.iteration_id = p.iteration_id
  LEFT JOIN planned_sp ps ON ps.issue_id = p.issue_id AND ps.iteration_id = p.iteration_id
  GROUP BY p.iteration_id
)

INSERT INTO fact_velocity (
    id,
    project_id,
    iteration_id,
    iteration_name,
    start_date,
    end_date,
    issue_type,
    custom_field_value,
    planned_story_points,
    completed_story_points,
    planned_issues,
    completed_issues
)
SELECT
  gen_random_uuid(),
  (SELECT project_id FROM params) AS project_id,
  it.id                           AS iteration_id,
  it.name                         AS iteration_name,
  it.start_date,
  it.end_date,
  NULL::text                      AS issue_type,
  NULL::text                      AS custom_field_value,
  COALESCE(pa.planned_story_points,0)   AS planned_story_points,
  COALESCE(ca.completed_story_points,0) AS completed_story_points,
  COALESCE(pa.planned_issues,0)         AS planned_issues,
  COALESCE(ca.completed_issues,0)       AS completed_issues
FROM iters it
LEFT JOIN planned_agg pa   ON pa.iteration_id = it.id
LEFT JOIN completed_agg ca ON ca.iteration_id = it.id
ORDER BY it.start_date, it.name;

COMMIT;
"""


# @anchor:dag:metrics_velocity:recalc_one
def recalc_velocity_for_project(project: Tuple[str, str]):
    project_id, project_key = project
    logging.info(f"Recalculating velocity for project {project_key} ({project_id})")
    pg = PostgresHook(postgres_conn_id="postgres_default")

    # Use one connection: temp table -> delete -> insert -> slices
    conn = pg.get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "CREATE TEMP TABLE IF NOT EXISTS tmp_current_project(project_id uuid) ON COMMIT DROP;"
        )
        cur.execute("TRUNCATE tmp_current_project;")
        cur.execute(
            "INSERT INTO tmp_current_project(project_id) VALUES (%s);", (project_id,)
        )
        # cleanup existing facts
        cur.execute(
            "DELETE FROM fact_velocity WHERE project_id = (SELECT project_id FROM tmp_current_project);"
        )
        # insert new facts using server-side query
        logging.info("Inserting fact_velocity (V2) for project %s", project_id)
        cur.execute(INSERT_SQL_V2_FROM_TMP)
        conn.commit()
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            logging.exception("Failed rollback after fact_velocity insert error")
        logging.exception(
            "Failed to recalc fact_velocity for project %s: %s", project_id, e
        )
        raise

    # 3) compute and write slices according to metric_slice_rules
    # Use server-side DO block (read project_id from tmp_current_project) to avoid client-side %-format conflicts
    slice_do = """
DO $$
DECLARE
  p_project_id uuid := (SELECT project_id FROM tmp_current_project);
  r RECORD;
  proj_rec RECORD;
  proj uuid;
BEGIN
  FOR r IN
    SELECT id, project_id AS rule_project_id, metric, slice_dim, top_n, group_other, max_distinct
    FROM metric_slice_rules
    WHERE enabled = true
      AND (metric = 'velocity' OR metric = 'all')
    ORDER BY (project_id IS NOT NULL) DESC
  LOOP
    -- build list of projects to process for this rule
    FOR proj_rec IN
      SELECT COALESCE(r.rule_project_id, p.id, p_project_id) AS project_id
      FROM projects p
      WHERE r.rule_project_id IS NOT NULL OR p_project_id IS NULL OR p.id = p_project_id
    LOOP
      proj := proj_rec.project_id;
      IF proj IS NULL THEN
        CONTINUE;
      END IF;

      -- cleanup leftover temps
      DROP TABLE IF EXISTS tmp_planned, tmp_ranked, tmp_top, tmp_skipped, tmp_completed, tmp_final_ok;

      -- 1) planned: compute plan as of sprint start using history (issue_iteration_history) and SP at sprint start
      CREATE TEMP TABLE tmp_planned ON COMMIT DROP AS
      WITH params AS (SELECT proj AS project_id),
      iters AS (
        SELECT it.* FROM iterations it WHERE it.project_id = (SELECT project_id FROM params)
          AND it.start_date IS NOT NULL AND it.end_date IS NOT NULL
      ),
      -- base membership pairs for iterations
      membership_base AS (
        SELECT DISTINCT ii.issue_id, ii.iteration_id
        FROM issue_iterations ii
        JOIN iters it ON it.id = ii.iteration_id
      ),
      -- last action for pair at or before sprint start
      state_at_start AS (
        SELECT m.issue_id, m.iteration_id,
               (
                 SELECT h.action
                 FROM issue_iteration_history h
                 JOIN iters it2 ON it2.id = h.iteration_id
                 WHERE h.issue_id = m.issue_id
                   AND h.iteration_id = m.iteration_id
                   AND h.changed_at <= (it2.start_date::timestamptz + interval '23:59:59')
                 ORDER BY h.changed_at DESC
                 LIMIT 1
               ) AS action_at_start
        FROM membership_base m
      ),
      planned_pairs AS (
        SELECT s.issue_id, s.iteration_id
        FROM state_at_start s
        JOIN iters it ON it.id = s.iteration_id
        JOIN issues i ON i.id = s.issue_id
        WHERE (s.action_at_start = 'added')
           OR (s.action_at_start IS NULL AND i.created::date <= it.start_date)
      ),
      sp_fields AS (
        SELECT id AS custom_field_id
        FROM custom_fields
        WHERE project_id = (SELECT project_id FROM params)
          AND (
            external_key IN ('customfield_10036','customfield_10016','story_points')
            OR LOWER(name) LIKE '%story point%'
          )
      ),
      planned_sp AS (
        SELECT p.issue_id, p.iteration_id,
               COALESCE(
                 (
                   SELECT CASE
                            WHEN jsonb_typeof(ch.new_value) = 'object' AND ch.new_value ? 'value' THEN NULLIF(ch.new_value->>'value','')::numeric
                            WHEN jsonb_typeof(ch.new_value) = 'number' THEN (ch.new_value)::numeric
                            WHEN jsonb_typeof(ch.new_value) = 'string' THEN NULLIF(trim(both '"' from ch.new_value::text),'')::numeric
                            ELSE NULL
                          END
                   FROM custom_field_history ch
                   JOIN iters it ON it.id = p.iteration_id
                   WHERE ch.issue_id = p.issue_id
                     AND ch.custom_field_id IN (SELECT custom_field_id FROM sp_fields)
                     AND ch.changed_at <= (it.start_date)::timestamptz + interval '23:59:59'
                   ORDER BY ch.changed_at DESC
                   LIMIT 1
                 ),
                 (
                   SELECT CASE
                            WHEN jsonb_typeof(cfv.value) = 'object' AND cfv.value ? 'value' THEN NULLIF(cfv.value->>'value','')::numeric
                            WHEN jsonb_typeof(cfv.value) = 'number' THEN (cfv.value)::numeric
                            WHEN jsonb_typeof(cfv.value) = 'string' THEN NULLIF(trim(both '"' from cfv.value::text),'')::numeric
                            ELSE NULL
                          END
                   FROM custom_field_values cfv
                   JOIN custom_fields cf ON cf.id = cfv.custom_field_id
                   WHERE cf.project_id = (SELECT project_id FROM params)
                     AND cf.id IN (SELECT custom_field_id FROM sp_fields)
                     AND cfv.issue_id = p.issue_id
                   LIMIT 1
                 ),
                 (SELECT i.estimate::numeric FROM issues i WHERE i.id = p.issue_id)
               ) AS story_points
        FROM planned_pairs p
      )
      SELECT
        (SELECT project_id FROM params) AS project_id,
        sp.iteration_id,
        CASE WHEN r.slice_dim = 'issue_type' THEN COALESCE(itype.name,'UNKNOWN') ELSE cfv_norm.val END AS slice_value,
        COUNT(DISTINCT sp.issue_id) AS planned_issues,
        SUM(COALESCE(sp.story_points,0)) AS planned_story_points
      FROM planned_sp sp
      JOIN issues iss ON iss.id = sp.issue_id
      LEFT JOIN issue_types itype ON itype.id = iss.type_id
      LEFT JOIN LATERAL (
        SELECT elem AS val FROM (
          SELECT jsonb_array_elements_text(cfv.value) AS elem
          FROM custom_fields cf
          JOIN custom_field_values cfv ON cfv.custom_field_id = cf.id AND cfv.issue_id = iss.id
          WHERE cf.project_id = (SELECT project_id FROM params) AND cf.external_key = regexp_replace(r.slice_dim,'^cf:','')
        ) t
        UNION ALL
        SELECT CASE WHEN cfv.value ? 'value' THEN cfv.value->>'value' ELSE trim(both '"' from cfv.value::text) END AS val
        FROM custom_fields cf
        JOIN custom_field_values cfv ON cfv.custom_field_id = cf.id AND cfv.issue_id = iss.id
        WHERE cf.project_id = (SELECT project_id FROM params) AND cf.external_key = regexp_replace(r.slice_dim,'^cf:','')
          AND jsonb_typeof(cfv.value) IS DISTINCT FROM 'array'
        LIMIT 1
      ) cfv_norm ON r.slice_dim LIKE 'cf:%'
      GROUP BY sp.iteration_id, CASE WHEN r.slice_dim = 'issue_type' THEN COALESCE(itype.name,'UNKNOWN') ELSE cfv_norm.val END;

      -- 2) ranking & distinct_count per iteration
      CREATE TEMP TABLE tmp_ranked ON COMMIT DROP AS
      SELECT p.*,
             ROW_NUMBER() OVER (PARTITION BY p.iteration_id ORDER BY p.planned_issues DESC) AS rn,
             COUNT(*) OVER (PARTITION BY p.iteration_id) AS distinct_count
      FROM tmp_planned p;

      -- 3) top_n and optionally OTHER
      CREATE TEMP TABLE tmp_top ON COMMIT DROP AS
      SELECT project_id, iteration_id, slice_value, planned_issues, planned_story_points, distinct_count
      FROM tmp_ranked WHERE rn <= r.top_n;

      IF r.group_other THEN
        INSERT INTO tmp_top (project_id, iteration_id, slice_value, planned_issues, planned_story_points, distinct_count)
        SELECT project_id, iteration_id, 'OTHER'::text, SUM(planned_issues)::int, SUM(planned_story_points)::numeric, MAX(distinct_count)
        FROM tmp_ranked WHERE rn > r.top_n GROUP BY project_id, iteration_id;
      END IF;

      -- 4) skipped iterations where too many distinct values
      CREATE TEMP TABLE tmp_skipped ON COMMIT DROP AS
      SELECT DISTINCT iteration_id FROM tmp_ranked WHERE distinct_count > r.max_distinct;

      -- 5) completed aggregation
      CREATE TEMP TABLE tmp_completed ON COMMIT DROP AS
      WITH params AS (SELECT proj AS project_id),
      end_statuses AS (
        SELECT DISTINCT s.id AS status_id
        FROM board_commitment_points cp
        JOIN board_columns bc ON bc.id = cp.board_column_id
        JOIN board_column_statuses bcs ON bcs.board_column_id = bc.id
        JOIN statuses s ON s.id = bcs.status_id
        JOIN boards b ON b.id = bc.board_id
        WHERE cp.role = 'commitment_end' AND b.project_id = (SELECT project_id FROM params)
      ),
      iters AS (
        SELECT it.* FROM iterations it WHERE it.project_id = (SELECT project_id FROM params) AND it.start_date IS NOT NULL AND it.end_date IS NOT NULL
      ),
      issues_in_sprint AS (
        SELECT DISTINCT i.id, i.estimate, ii.iteration_id, i.current_status_id, i.resolved
        FROM issues i
        JOIN issue_iterations ii ON ii.issue_id = i.id
        JOIN iters it ON it.id = ii.iteration_id
      ),
      done_by_history AS (
        SELECT i.id AS issue_id, ii.iteration_id, MIN(h.changed_at) AS completion_ts
        FROM issues i
        JOIN issue_status_history h ON h.issue_id = i.id
        JOIN end_statuses es ON es.status_id = h.to_status_id
        JOIN issue_iterations ii ON ii.issue_id = i.id
        JOIN iters it ON it.id = ii.iteration_id
        WHERE h.changed_at::date <= it.end_date
        GROUP BY i.id, ii.iteration_id
      ),
      done_by_current AS (
        SELECT isp.id AS issue_id, isp.iteration_id
        FROM issues_in_sprint isp
        JOIN end_statuses es ON es.status_id = isp.current_status_id
      ),
      done_by_resolution AS (
        SELECT isp.id AS issue_id, isp.iteration_id
        FROM issues_in_sprint isp
        JOIN iters it ON it.id = isp.iteration_id
        WHERE isp.resolved IS NOT NULL AND isp.resolved::date <= it.end_date
      ),
      done_union AS (
        SELECT dh.issue_id, dh.iteration_id
        FROM done_by_history dh
        JOIN iters it ON it.id = dh.iteration_id
        WHERE it.end_date < CURRENT_DATE

        UNION
        SELECT dr.issue_id, dr.iteration_id
        FROM done_by_resolution dr
        JOIN iters it ON it.id = dr.iteration_id
        WHERE it.end_date < CURRENT_DATE

        UNION
        SELECT dh.issue_id, dh.iteration_id
        FROM done_by_history dh
        JOIN iters it ON it.id = dh.iteration_id
        WHERE it.start_date <= CURRENT_DATE AND it.end_date >= CURRENT_DATE

        UNION
        SELECT dc.issue_id, dc.iteration_id
        FROM done_by_current dc
        JOIN iters it ON it.id = dc.iteration_id
        WHERE it.start_date <= CURRENT_DATE AND it.end_date >= CURRENT_DATE

        UNION
        SELECT dr.issue_id, dr.iteration_id
        FROM done_by_resolution dr
        JOIN iters it ON it.id = dr.iteration_id
        WHERE it.start_date <= CURRENT_DATE AND it.end_date >= CURRENT_DATE
      )
      SELECT (SELECT project_id FROM params) AS project_id,
             sp.iteration_id,
             CASE WHEN r.slice_dim = 'issue_type' THEN COALESCE(itype.name,'UNKNOWN') ELSE cfv_norm.val END AS slice_value,
             COUNT(DISTINCT sp.issue_id) AS completed_issues,
             SUM(COALESCE(sp.story_points,0)) AS completed_story_points
      FROM (
        SELECT isp.issue_id, isp.iteration_id,
          COALESCE(i.estimate,
            (SELECT (cfv.value->>'value')::numeric FROM custom_fields cf
             JOIN custom_field_values cfv ON cfv.custom_field_id = cf.id AND cfv.issue_id = isp.issue_id
             WHERE cf.project_id = (SELECT project_id FROM params) AND cf.external_key = 'story_points' LIMIT 1)
          ) AS story_points
        FROM issue_iterations isp
        JOIN iters it ON it.id = isp.iteration_id
        JOIN issues i ON i.id = isp.issue_id
      ) sp
      JOIN done_union du ON du.issue_id = sp.issue_id AND du.iteration_id = sp.iteration_id
      LEFT JOIN issues iss ON iss.id = sp.issue_id
      LEFT JOIN issue_types itype ON itype.id = iss.type_id
      LEFT JOIN LATERAL (
        SELECT arr.elem AS val FROM custom_fields cf
        JOIN custom_field_values cfv ON cfv.custom_field_id = cf.id AND cfv.issue_id = iss.id
        CROSS JOIN LATERAL (SELECT jsonb_array_elements_text(cfv.value) AS elem) arr
        WHERE cf.project_id = (SELECT project_id FROM params) AND cf.external_key = regexp_replace(r.slice_dim, '^cf:', '')
        UNION ALL
        SELECT CASE WHEN cfv.value ? 'value' THEN cfv.value->>'value' ELSE trim(both '"' from cfv.value::text) END AS val
        FROM custom_fields cf
        JOIN custom_field_values cfv ON cfv.custom_field_id = cf.id AND cfv.issue_id = iss.id
        WHERE cf.project_id = (SELECT project_id FROM params) AND cf.external_key = regexp_replace(r.slice_dim, '^cf:', '')
          AND jsonb_typeof(cfv.value) IS DISTINCT FROM 'array'
        LIMIT 1
      ) cfv_norm ON r.slice_dim LIKE 'cf:%'
      GROUP BY sp.iteration_id, CASE WHEN r.slice_dim = 'issue_type' THEN COALESCE(itype.name,'UNKNOWN') ELSE cfv_norm.val END;

      -- 6) construct final_ok (exclude skipped iterations) and write
      CREATE TEMP TABLE tmp_final_ok ON COMMIT DROP AS
      SELECT p.project_id, p.iteration_id, it.name AS iteration_name, it.start_date, it.end_date,
             p.slice_value, p.planned_issues, p.planned_story_points,
             COALESCE(c.completed_issues,0) AS completed_issues,
             COALESCE(c.completed_story_points,0) AS completed_story_points
      FROM tmp_top p
      LEFT JOIN tmp_completed c ON c.iteration_id = p.iteration_id AND c.slice_value = p.slice_value
      JOIN iterations it ON it.id = p.iteration_id
      WHERE p.iteration_id NOT IN (SELECT iteration_id FROM tmp_skipped);

      DELETE FROM fact_velocity_slice f
      USING (SELECT DISTINCT iteration_id FROM tmp_final_ok) d
      WHERE f.project_id = proj
        AND f.iteration_id = d.iteration_id
        AND f.slice_dim = r.slice_dim;

      INSERT INTO fact_velocity_slice (
        id, project_id, iteration_id, iteration_name, start_date, end_date,
        slice_dim, slice_value, planned_issues, planned_story_points, completed_issues, completed_story_points, created_at
      )
      SELECT gen_random_uuid(), project_id, iteration_id, iteration_name, start_date, end_date,
             r.slice_dim::text, slice_value, planned_issues, planned_story_points, completed_issues, completed_story_points, now()
      FROM tmp_final_ok;

      RAISE NOTICE 'Velocity rule % processed for project %: inserted=%', r.id, proj, (SELECT COUNT(*) FROM tmp_final_ok);

      DROP TABLE IF EXISTS tmp_planned, tmp_ranked, tmp_top, tmp_skipped, tmp_completed, tmp_final_ok;
    END LOOP; -- end projects loop
  END LOOP; -- end rules loop
END;
$$ LANGUAGE plpgsql;
"""

    conn = pg.get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "CREATE TEMP TABLE IF NOT EXISTS tmp_current_project(project_id uuid) ON COMMIT DROP;"
        )
        cur.execute("TRUNCATE tmp_current_project;")
        cur.execute(
            "INSERT INTO tmp_current_project(project_id) VALUES (%s);", (project_id,)
        )
        logging.info("Executing velocity slice DO for project %s", project_id)
        cur.execute(slice_do)
        conn.commit()
        # log server notices (RAISE NOTICE) to help debugging
        try:
            notices = conn.notices if hasattr(conn, "notices") else []
            if notices:
                logging.info("Postgres notices (last 20): %s", notices[-20:])
        except Exception:
            logging.exception("Failed to read Postgres notices")
        # quick verify rows inserted into fact_velocity_slice for this project
        try:
            cur.execute(
                "SELECT COUNT(*) FROM fact_velocity_slice WHERE project_id = %s",
                (project_id,),
            )
            cnt = cur.fetchone()[0]
            logging.info("fact_velocity_slice rows for project %s: %s", project_id, cnt)
        except Exception:
            logging.exception("Failed to count fact_velocity_slice")
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            logging.exception("Failed rollback after velocity slice DO error")
        logging.exception(
            "Velocity slice generation failed for project %s: %s", project_id, e
        )
        raise
    finally:
        try:
            cur.close()
        except Exception:
            logging.exception("Failed to close cursor")
        try:
            conn.close()
        except Exception:
            logging.exception("Failed to close connection")
    logging.info(f"Velocity recalculated for {project_key}")


# @anchor:dag:metrics_velocity:recalc_all
def recalc_all(**kwargs):
    ti = kwargs["ti"]
    projects = ti.xcom_pull(key="projects", task_ids="get_projects") or []
    conf = (kwargs.get("dag_run") or {}).conf or {}
    date_from = conf.get("date_from")
    date_to = conf.get("date_to")
    if not projects:
        logging.warning("No projects to process — exiting")
        return
    if date_from or date_to:
        logging.info(f"Using date filter: from={date_from} to={date_to}")
    # Mirror lead_time behavior: call per-project worker that also runs slice generation
    for p in projects:
        try:
            recalc_velocity_for_project(p)
        except Exception as e:
            logging.exception("Failed to recalc velocity for project %s: %s", p, e)
            # continue with next project
            continue


# @anchor:dag:metrics_velocity:dag
with DAG(
    "metrics_velocity_recalculate",
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,  # ручной запуск по требованию
    catchup=False,
    tags=["metrics", "facts", "velocity"],
    default_args={
        "retries": 1,
        "retry_delay": timedelta(minutes=1),
    },
    description="Перерасчет fact_velocity без БД-функций и триггеров",
) as dag:
    # @anchor:dag:metrics_velocity:tasks
    t_get = PythonOperator(task_id="get_projects", python_callable=get_projects)
    t_recalc = PythonOperator(
        task_id="recalculate_velocity", python_callable=recalc_all
    )

    # @anchor:dag:metrics_velocity:deps
    t_get >> t_recalc
