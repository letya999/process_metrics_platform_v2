import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook


# @anchor:dag:metrics_lead_time:get_projects
def get_projects(**kwargs):
    """Возвращает список проектов для перерасчета lead_time.

    Поддерживает фильтр `project_keys` из dag_run.conf.
    Возвращает список пар (project_id, project_key)
    """
    pg = PostgresHook(postgres_conn_id="postgres_default")
    conf = (kwargs.get("dag_run") or {}).conf or {}
    filter_keys = conf.get("project_keys") if isinstance(conf, dict) else None
    if filter_keys and not isinstance(filter_keys, list):
        filter_keys = [filter_keys]

    base_sql = """
        SELECT id::text, external_key
        FROM projects
        WHERE 1=1
    """
    params = []
    if filter_keys:
        placeholders = ",".join(["%s"] * len(filter_keys))
        if all(isinstance(k, str) and len(k) == 36 and "-" in k for k in filter_keys):
            base_sql += f" AND id IN ({placeholders})"
        else:
            base_sql += f" AND external_key IN ({placeholders})"
        params.extend(filter_keys)

    rows = pg.get_records(base_sql, parameters=tuple(params) if params else None)
    if not rows:
        logging.warning("No projects found for metrics lead_time recalculation")
    else:
        logging.info(f"Selected {len(rows)} projects: {[r[1] for r in rows]}")

    kwargs["ti"].xcom_push(key="projects", value=rows)
    return rows


# @anchor:dag:metrics_lead_time:sql
LEAD_TIME_SQL = """
-- Полный пересчёт fact_lead_time / fact_lead_time_bins для одного проекта
-- Использует board_commitment_points, board_columns, board_column_statuses
-- Параметры: project_id, (date_from, date_to) не используются сейчас, но оставлены для совместимости

WITH
params AS (
  SELECT %s::uuid AS project_id
),

points AS (
  SELECT s.project_id, s.board_id,
         s.board_column_id AS start_column_id, s.order_num AS start_order,
         e.board_column_id AS end_column_id, e.order_num AS end_order
  FROM (
      SELECT b.project_id, bc.board_id, bc.id AS board_column_id, bc.order_num
      FROM board_commitment_points cp
      JOIN board_columns bc ON bc.id = cp.board_column_id
      JOIN boards b ON b.id = bc.board_id
      WHERE cp.role = 'commitment_start'
  ) s
  JOIN (
      SELECT b.project_id, bc.board_id, bc.id AS board_column_id, bc.order_num
      FROM board_commitment_points cp
      JOIN board_columns bc ON bc.id = cp.board_column_id
      JOIN boards b ON b.id = bc.board_id
      WHERE cp.role = 'commitment_end'
  ) e ON e.project_id = s.project_id AND e.board_id = s.board_id
  WHERE s.order_num < e.order_num
    AND s.project_id = (SELECT project_id FROM params)
),

column_statuses AS (
  SELECT bc.id AS board_column_id, s.id AS status_id, bc.order_num
  FROM board_column_statuses bcs
  JOIN board_columns bc ON bc.id = bcs.board_column_id
  JOIN statuses s ON s.id = bcs.status_id
  WHERE s.project_id = (SELECT project_id FROM params)
),

issues_src AS (
  SELECT i.id AS issue_id, i.project_id, i.created, i.resolved
  FROM issues i
  WHERE i.project_id = (SELECT project_id FROM params)
),

last_left_end AS (
  SELECT isrc.issue_id, MAX(h.changed_at) AS left_at
  FROM issues_src isrc
  JOIN issue_status_history h ON h.issue_id = isrc.issue_id
  JOIN points p ON p.project_id = isrc.project_id
  JOIN column_statuses cs_from ON cs_from.status_id = h.from_status_id
  WHERE cs_from.board_column_id = p.end_column_id
    AND NOT EXISTS (
        SELECT 1 FROM column_statuses cs2
        WHERE cs2.status_id = h.to_status_id
          AND cs2.board_column_id = p.end_column_id
    )
    AND h.from_status_id IS DISTINCT FROM h.to_status_id
  GROUP BY isrc.issue_id
),

end_event_hist AS (
  SELECT DISTINCT ON (isrc.issue_id)
         isrc.issue_id,
         h.changed_at AS end_at,
         cp_end.id AS end_cp_id
  FROM issues_src isrc
  LEFT JOIN last_left_end lle ON lle.issue_id = isrc.issue_id
  JOIN issue_status_history h ON h.issue_id = isrc.issue_id
  JOIN points p ON p.project_id = isrc.project_id
  JOIN column_statuses cs_to ON cs_to.status_id = h.to_status_id
  LEFT JOIN board_commitment_points cp_end ON cp_end.board_column_id = cs_to.board_column_id AND cp_end.role = 'commitment_end'
  WHERE cs_to.board_column_id = p.end_column_id
    AND h.changed_at > COALESCE(lle.left_at, '-infinity')
    AND (isrc.resolved IS NULL OR h.changed_at <= isrc.resolved)
    AND h.from_status_id IS DISTINCT FROM h.to_status_id
  ORDER BY isrc.issue_id, h.changed_at ASC
),

end_event AS (
  SELECT isrc.issue_id,
         COALESCE(eh.end_at, isrc.resolved) AS end_at,
         eh.end_cp_id AS end_cp_id
  FROM issues_src isrc
  LEFT JOIN end_event_hist eh ON eh.issue_id = isrc.issue_id
  WHERE COALESCE(eh.end_at, isrc.resolved) IS NOT NULL
),

start_event_hist AS (
  SELECT DISTINCT ON (isrc.issue_id)
         isrc.issue_id,
         h.changed_at AS start_at,
         cp_start.id AS start_cp_id
  FROM issues_src isrc
  JOIN end_event e ON e.issue_id = isrc.issue_id
  JOIN issue_status_history h ON h.issue_id = isrc.issue_id
  JOIN points p ON p.project_id = isrc.project_id
  JOIN column_statuses cs ON cs.status_id = h.to_status_id
  LEFT JOIN board_commitment_points cp_start ON cp_start.board_column_id = cs.board_column_id AND cp_start.role = 'commitment_start'
  WHERE cs.order_num >= p.start_order
    AND cs.order_num <  p.end_order
    AND h.changed_at <= e.end_at
    AND h.from_status_id IS DISTINCT FROM h.to_status_id
  ORDER BY isrc.issue_id, h.changed_at ASC
),

start_event AS (
  SELECT
    isrc.issue_id,
    COALESCE(sh.start_at, isrc.created) AS start_at,
    sh.start_cp_id
  FROM issues_src isrc
  JOIN end_event e ON e.issue_id = isrc.issue_id
  LEFT JOIN start_event_hist sh ON sh.issue_id = isrc.issue_id
  WHERE COALESCE(sh.start_at, isrc.created) IS NOT NULL
),

lead AS (
  SELECT
    i.project_id,
    i.issue_id,
    s.start_at,
    e.end_at,
    s.start_cp_id AS start_status_commitment_point_id,
    e.end_cp_id   AS end_status_commitment_point_id,
    EXTRACT(EPOCH FROM (e.end_at - s.start_at))/86400.0 AS lead_time_days
  FROM issues_src i
  JOIN start_event s ON s.issue_id = i.issue_id
  JOIN end_event   e ON e.issue_id = i.issue_id
  WHERE e.end_at >= s.start_at
),

lead_with_bins AS (
  SELECT
    project_id,
    issue_id,
    start_at,
    end_at,
    lead_time_days,
    start_status_commitment_point_id,
    end_status_commitment_point_id,
    GREATEST(1, CEIL(lead_time_days))::int AS bin_number
  FROM lead
),

bins_agg AS (
  SELECT project_id, bin_number, COUNT(*) AS tickets_count
  FROM lead_with_bins
  GROUP BY project_id, bin_number
),

ins_bins AS (
  INSERT INTO public.fact_lead_time_bins (id, project_id, bin_number, tickets_count)
  SELECT gen_random_uuid(), project_id, bin_number, tickets_count
  FROM bins_agg
  RETURNING id, project_id, bin_number
)

INSERT INTO public.fact_lead_time (
  id, project_id, issue_id,
  lead_time_days,
  commitment_start_at,
  commitment_end_at,
  start_status_commitment_point_id,
  end_status_commitment_point_id,
  lead_time_bin_id
)
SELECT
  gen_random_uuid(),
  l.project_id,
  l.issue_id,
  l.lead_time_days,
  l.start_at,
  l.end_at,
  l.start_status_commitment_point_id,
  l.end_status_commitment_point_id,
  b.id
FROM lead_with_bins l
JOIN ins_bins b
  ON b.project_id = l.project_id
AND b.bin_number = l.bin_number;
"""


# @anchor:dag:metrics_lead_time:recalc_one
def recalc_lead_time_for_project(project):
    project_id, project_key = project
    logging.info(f"Recalculating lead_time for project {project_key} ({project_id})")
    pg = PostgresHook(postgres_conn_id="postgres_default")

    # очистка фактов по проекту
    pg.run(
        "DELETE FROM public.fact_lead_time WHERE project_id = %s::uuid",
        parameters=(project_id,),
    )
    pg.run(
        "DELETE FROM public.fact_lead_time_bins WHERE project_id = %s::uuid",
        parameters=(project_id,),
    )

    # запуск пересчёта
    pg.run(LEAD_TIME_SQL, parameters=(project_id,))
    logging.info(f"Lead time recalculated for {project_key}")
    # compute slices according to metric_slice_rules (lead_time)
    try:
        slice_do = """
DO $$
DECLARE
  p_project_id uuid := (SELECT project_id FROM tmp_current_project); -- read project_id from temp table
  r RECORD;
  proj uuid;
BEGIN
  FOR r IN
    SELECT id, (NULLIF(project_id::text, 'all'))::uuid AS rule_project_id, metric, slice_dim, top_n, group_other, max_distinct
    FROM metric_slice_rules
    WHERE enabled = true
      AND (metric = 'lead_time' OR metric = 'all')
    ORDER BY (project_id IS NOT NULL) DESC
  LOOP
    -- prepare list of projects to process for this rule
    CREATE TEMP TABLE IF NOT EXISTS tmp_projects_to_run(project_id uuid) ON COMMIT DROP;
    TRUNCATE TABLE tmp_projects_to_run;
    IF r.rule_project_id IS NOT NULL THEN
      INSERT INTO tmp_projects_to_run SELECT r.rule_project_id;
    ELSIF p_project_id IS NOT NULL THEN
      INSERT INTO tmp_projects_to_run SELECT p_project_id;
    ELSE
      INSERT INTO tmp_projects_to_run SELECT id FROM projects;
    END IF;

    FOR proj IN SELECT project_id FROM tmp_projects_to_run LOOP

      IF r.slice_dim = 'issue_type' THEN
      RAISE NOTICE 'Processing lead_time slice rule % for project %: slice_dim=% top_n=% group_other=% max_distinct=%', r.id, proj, r.slice_dim, r.top_n, r.group_other, r.max_distinct;

      CREATE TEMP TABLE tmp_agg ON COMMIT DROP AS
      SELECT
        flt.project_id,
        ji.iteration_id,
        COALESCE(it.name, 'UNKNOWN') AS slice_value,
        COUNT(*)::int AS count_tickets
      FROM fact_lead_time flt
      LEFT JOIN issues iss ON iss.id = flt.issue_id
      LEFT JOIN issue_types it ON it.id = iss.type_id
      LEFT JOIN LATERAL (
        SELECT ii.iteration_id
        FROM issue_iterations ii
        JOIN iterations it2 ON it2.id = ii.iteration_id
        WHERE ii.issue_id = flt.issue_id
          AND it2.project_id = flt.project_id
        ORDER BY it2.start_date DESC
        LIMIT 1
      ) ji ON true
      WHERE flt.project_id = proj
      GROUP BY flt.project_id, ji.iteration_id, COALESCE(it.name,'UNKNOWN');

      CREATE TEMP TABLE tmp_ranked ON COMMIT DROP AS
      SELECT a.*, ROW_NUMBER() OVER (PARTITION BY a.iteration_id ORDER BY a.count_tickets DESC) AS rn,
             COUNT(*) OVER (PARTITION BY a.iteration_id) AS distinct_count
      FROM tmp_agg a;

      CREATE TEMP TABLE tmp_final_map ON COMMIT DROP AS
      SELECT project_id, iteration_id, slice_value, count_tickets
      FROM tmp_ranked
      WHERE rn <= r.top_n;

      IF r.group_other THEN
        INSERT INTO tmp_final_map (project_id, iteration_id, slice_value, count_tickets)
        SELECT project_id, iteration_id, 'OTHER'::text AS slice_value, SUM(count_tickets)::int
        FROM tmp_ranked
        WHERE rn > r.top_n
        GROUP BY project_id, iteration_id;
      END IF;

      CREATE TEMP TABLE tmp_skipped_iters ON COMMIT DROP AS
      SELECT DISTINCT iteration_id FROM tmp_ranked WHERE distinct_count > r.max_distinct;

      DELETE FROM fact_lead_time_slice f
      USING (SELECT DISTINCT iteration_id FROM tmp_final_map) d
      WHERE f.project_id = proj
        AND f.iteration_id = d.iteration_id
        AND f.slice_dim = r.slice_dim
        AND d.iteration_id NOT IN (SELECT iteration_id FROM tmp_skipped_iters);

      INSERT INTO fact_lead_time_slice (
        id, project_id, issue_id, iteration_id,
        lead_time_days, commitment_start_at, commitment_end_at,
        start_status_commitment_point_id, end_status_commitment_point_id,
        lead_time_bin_id, slice_dim, slice_value, created_at
      )
      SELECT
        gen_random_uuid(),
        flt.project_id,
        flt.issue_id,
        ji.iteration_id,
        flt.lead_time_days,
        flt.commitment_start_at,
        flt.commitment_end_at,
        flt.start_status_commitment_point_id,
        flt.end_status_commitment_point_id,
        flt.lead_time_bin_id,
        r.slice_dim::text,
        COALESCE(m.slice_value, CASE WHEN r.group_other THEN 'OTHER' ELSE NULL END)::text,
        now()
      FROM fact_lead_time flt
      LEFT JOIN issues iss ON iss.id = flt.issue_id
      LEFT JOIN issue_types it ON it.id = iss.type_id
      LEFT JOIN LATERAL (
        SELECT ii.iteration_id
        FROM issue_iterations ii
        JOIN iterations it2 ON it2.id = ii.iteration_id
        WHERE ii.issue_id = flt.issue_id
          AND it2.project_id = flt.project_id
        ORDER BY it2.start_date DESC
        LIMIT 1
      ) ji ON true
      LEFT JOIN LATERAL (
        SELECT tf.slice_value
        FROM tmp_final_map tf
        WHERE tf.iteration_id = ji.iteration_id
          AND tf.slice_value = COALESCE(it.name,'UNKNOWN')
        LIMIT 1
      ) m ON true
      WHERE flt.project_id = proj
        AND ji.iteration_id NOT IN (SELECT iteration_id FROM tmp_skipped_iters);

      DELETE FROM fact_lead_time_bins_slice b
      WHERE b.project_id = proj
        AND b.slice_dim = r.slice_dim;

      INSERT INTO fact_lead_time_bins_slice (id, project_id, slice_dim, slice_value, bin_number, tickets_count, created_at)
      SELECT
        gen_random_uuid(),
        flt.project_id,
        r.slice_dim::text,
        COALESCE(m.slice_value, CASE WHEN r.group_other THEN 'OTHER' ELSE NULL END)::text,
        bins.bin_number,
        COUNT(*)::int,
        now()
      FROM fact_lead_time flt
      JOIN fact_lead_time_bins bins ON bins.id = flt.lead_time_bin_id
      LEFT JOIN issues iss ON iss.id = flt.issue_id
      LEFT JOIN issue_types it ON it.id = iss.type_id
      LEFT JOIN LATERAL (
        SELECT ii.iteration_id
        FROM issue_iterations ii
        JOIN iterations it2 ON it2.id = ii.iteration_id
        WHERE ii.issue_id = flt.issue_id
          AND it2.project_id = flt.project_id
        ORDER BY it2.start_date DESC
        LIMIT 1
      ) ji ON true
      LEFT JOIN LATERAL (
        SELECT tf.slice_value
        FROM tmp_final_map tf
        WHERE tf.iteration_id = ji.iteration_id
          AND tf.slice_value = COALESCE(it.name,'UNKNOWN')
        LIMIT 1
      ) m ON true
      WHERE flt.project_id = proj
        AND ji.iteration_id NOT IN (SELECT iteration_id FROM tmp_skipped_iters)
      GROUP BY flt.project_id, bins.bin_number, COALESCE(m.slice_value, CASE WHEN r.group_other THEN 'OTHER' ELSE NULL END);

      RAISE NOTICE 'Rule % processed for project %: skipped_iterations=%', r.id, proj, (SELECT COUNT(*) FROM tmp_skipped_iters);

    ELSE
      RAISE NOTICE 'Skipping rule % for project %: unsupported slice_dim=% (only issue_type handled here)', r.id, proj, r.slice_dim;
    END IF;
  END LOOP; -- end proj loop
  END LOOP; -- end rules loop
END
$$ LANGUAGE plpgsql;
"""
        # execute server-side slice runner for this project
        # create a temp table with the project_id and let the DO block read it
        conn = pg.get_conn()
        cur = conn.cursor()
        try:
            logging.debug("Preparing tmp_current_project for project %s", project_id)
            cur.execute(
                "CREATE TEMP TABLE IF NOT EXISTS tmp_current_project(project_id uuid) ON COMMIT DROP;"
            )
            cur.execute("TRUNCATE tmp_current_project;")
            cur.execute(
                "INSERT INTO tmp_current_project(project_id) VALUES (%s);",
                (project_id,),
            )
            logging.info(
                "Executing slice_do for project %s (len=%d)", project_id, len(slice_do)
            )
            logging.debug(slice_do[:2000])
            cur.execute(slice_do)
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                logging.exception("Failed to rollback connection after slice_do error")
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
    except Exception as e:
        logging.exception(f"Slice generation for lead_time failed: {e}")


# @anchor:dag:metrics_lead_time:recalc_all
def recalc_all(**kwargs):
    ti = kwargs["ti"]
    projects = ti.xcom_pull(key="projects", task_ids="get_projects") or []
    if not projects:
        logging.warning("No projects to process — exiting")
        return

    for p in projects:
        try:
            recalc_lead_time_for_project(p)
        except Exception as e:
            logging.exception("Failed to recalc lead_time for project %s: %s", p, e)
            # continue with next project
            continue


with DAG(
    "metrics_lead_time_recalculate",
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,  # manual by default; change to cron if needed
    catchup=False,
    tags=["metrics", "facts", "lead_time"],
    default_args={
        "retries": 1,
        "retry_delay": timedelta(minutes=1),
    },
    description="Перерасчет fact_lead_time и fact_lead_time_bins",
) as dag:
    t_get = PythonOperator(task_id="get_projects", python_callable=get_projects)
    t_recalc = PythonOperator(
        task_id="recalculate_lead_time", python_callable=recalc_all
    )

    t_get >> t_recalc
