from airflow import DAG
from airflow.operators.python import PythonOperator, ShortCircuitOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.exceptions import AirflowException
from airflow.models.param import Param
import os
from datetime import datetime, timedelta
import logging

# @anchor:dag:utils:db_helpers
def _table_exists(pg, schema_name, table_name) -> bool:
    try:
        row = pg.get_first(
            """
            SELECT EXISTS (
              SELECT 1
              FROM information_schema.tables
              WHERE table_schema = %s AND table_name = %s
            );
            """,
            parameters=(schema_name, table_name),
        )
        return bool(row and row[0])
    except Exception:
        return False


# @anchor:dag:utils:column_helpers
def _has_columns(pg, schema_name, table_name, required_columns) -> bool:
    try:
        cols = pg.get_records(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            """,
            parameters=(schema_name, table_name),
        )
        present = {c[0] for c in cols}
        return all(col in present for col in required_columns)
    except Exception:
        return False


# @anchor:dag:utils:get_conf
def _get_conf(kwargs):
    dag_run = kwargs.get('dag_run')
    conf = {}
    if dag_run is not None and getattr(dag_run, 'conf', None):
        conf = dag_run.conf or {}
    if not conf:
        # Fallback to Airflow Params when conf is not provided in Trigger modal
        conf = kwargs.get('params') or {}
    if not isinstance(conf, dict):
        return {}

    # Normalize helpers
    def _norm_optional(value):
        if isinstance(value, str):
            lv = value.strip()
            if lv == "":
                return None
            lvl = lv.lower()
            if lvl in {"null", "none", "nan"}:
                return None
        return value

    def _norm_bool(value, default=False):
        if isinstance(value, str):
            v = value.strip().lower()
            if v in {"1", "true", "yes", "y", "on"}:
                return True
            if v in {"0", "false", "no", "n", "off"}:
                return False
        return bool(value) if value is not None else default

    # Required fields: user_id, integration_uuid, project_uuids (str or list)
    user_id = _norm_optional(conf.get('user_id'))
    integration_uuid = _norm_optional(conf.get('integration_uuid'))

    proj_val = conf.get('project_uuids')
    import re

    def _normalize_project_uuids_value(raw):
        if not raw:
            return []
        if isinstance(raw, str):
            parts = re.split(r"[,;]\s*", raw.strip())
            return [p for p in (p.strip() for p in parts) if p]
        if isinstance(raw, list):
            out = []
            for item in raw:
                if not item:
                    continue
                if isinstance(item, str) and ("," in item or ";" in item):
                    parts = re.split(r"[,;]\s*", item)
                    out.extend([p for p in (p.strip() for p in parts) if p])
                else:
                    s = str(item).strip()
                    if s:
                        out.append(s)
            return out
        return []

    project_uuids = _normalize_project_uuids_value(proj_val)

    # Strict UUID format quick-check
    def _is_uuid(v: str) -> bool:
        try:
            s = str(v)
            return len(s) == 36 and s.count('-') == 4
        except Exception:
            return False

    missing = []
    if not user_id or not _is_uuid(user_id):
        missing.append('user_id')
    if not integration_uuid or not _is_uuid(integration_uuid):
        missing.append('integration_uuid')
    if not project_uuids or any(not _is_uuid(pid) for pid in project_uuids):
        missing.append('project_uuids')
    if missing:
        raise AirflowException(
            "Invalid or missing parameters: " + ", ".join(missing) + \
            ". Provide: user_id=<uuid>, integration_uuid=<uuid>, project_uuids=[<uuid>, ...]"
        )

    # Dates and extras
    date_from = _norm_optional(conf.get('date_from'))
    date_to = _norm_optional(conf.get('date_to'))
    mode = conf.get('mode')  # manual | auto_single | auto_multi (optional)
    full_recompute = _norm_bool(conf.get('full_recompute'), default=False)

    # Back-compat: expose project_keys for downstream functions, but it's strictly UUIDs
    conf_out = {
        'user_id': user_id,
        'integration_uuid': integration_uuid,
        'project_uuids': project_uuids,
        'project_keys': list(project_uuids),  # legacy variable name used in SQL builders
        'date_from': date_from,
        'date_to': date_to,
        'mode': mode,
        'full_recompute': full_recompute,
        # Manual loader by default should NOT narrow by dates; can be enabled via conf
        'apply_filters': bool(conf.get('apply_filters')) if isinstance(conf, dict) else False,
    }
    return conf_out


# @anchor:dag:utils:is_uuid
def _looks_like_uuid(value: str) -> bool:
    try:
        v = str(value)
        return len(v) == 36 and v.count('-') == 4
    except Exception:
        return False

# @anchor:dag:check_schema_or_fail
def check_schema_or_fail() -> None:
    pg = PostgresHook(postgres_conn_id='postgres_default')
    required = [
        ('public', 'projects'),
        ('public', 'statuses'),
        ('public', 'issue_types'),
        ('public', 'iteration_types'),
        ('public', 'iteration_statuses'),
        ('public', 'iterations'),
        ('public', 'issues'),
        ('public', 'custom_fields'),
    ]
    missing = []
    for schema_name, table_name in required:
        if not _table_exists(pg, schema_name, table_name):
            missing.append(f"{schema_name}.{table_name}")
    if missing:
        try:
            db_info = pg.get_first("SELECT current_database(), current_user;")
            db_name, db_user = (db_info or (None, None))
        except Exception:
            db_name, db_user = None, None
        msg = f"Schema check failed, missing tables: {missing}. Connected DB={db_name}, USER={db_user}. Ensure connection 'postgres_default' points to metrics DB."
        logging.error(msg)
        # Fail fast instead of skipping downstream tasks
        raise AirflowException(msg)
    logging.info("Schema check passed")

# @anchor:dag:jira_full_loader_manual
def load_statuses(**kwargs):
    """Загружает статусы из raw_jira в таблицу statuses"""
    pg_hook = PostgresHook(postgres_conn_id='postgres_default')
    
    # Проверяем структуру таблицы project_statuses__raw_data__statuses
    check_columns_sql = """
    SELECT column_name 
    FROM information_schema.columns 
    WHERE table_schema = 'raw_jira' 
    AND table_name = 'project_statuses__raw_data__statuses'
    ORDER BY ordinal_position;
    """
    
    columns = pg_hook.get_records(check_columns_sql)
    column_names = [col[0] for col in columns]
    logging.info(f"Available columns in project_statuses__raw_data__statuses: {column_names}")
    
    # Определяем правильное название колонки для категории
    category_column = None
    if 'status_category__name' in column_names:
        category_column = 'ps.status_category__name'
    elif 'status_category' in column_names:
        category_column = 'ps.status_category'
    else:
        category_column = "'To Do'"  # fallback
    
    conf = _get_conf(kwargs)
    # Debug issue logging is disabled to avoid NameError and noisy debug output
    debug_issue_key = None
    filter_keys = conf.get('project_keys') if isinstance(conf, dict) else None
    user_id = conf.get('user_id') if isinstance(conf, dict) else None
    integration_uuid = conf.get('integration_uuid') if isinstance(conf, dict) else None
    if filter_keys and not isinstance(filter_keys, list):
        filter_keys = [filter_keys]

    where_projects = "WHERE ps.name IS NOT NULL"
    params = []
    if filter_keys:
        placeholders = ','.join(['%s'] * len(filter_keys))
        if all(_looks_like_uuid(k) for k in filter_keys):
            where_projects += f" AND p.id IN ({placeholders})"
        else:
            where_projects += f" AND p.external_key IN ({placeholders})"
        params.extend(filter_keys)
    if user_id and _looks_like_uuid(user_id):
        where_projects += " AND p.user_id = %s::uuid"
        params.append(user_id)
    if integration_uuid and _looks_like_uuid(integration_uuid):
        where_projects += " AND p.tool_integration_id = %s::uuid"
        params.append(integration_uuid)

    # Debug: if a sample issue_key provided via env (DEBUG_ISSUE_KEY), show before/after rows for it
    debug_issue_key = os.getenv('DEBUG_ISSUE_KEY')
    if False:
        try:
            logging.info(f"DEBUG: selecting raw and public rows for {debug_issue_key} BEFORE insert")
            pre_raw = pg_hook.get_first("SELECT issue_key, created, updated, resolution_date FROM raw_jira.issues WHERE issue_key = %s", parameters=(debug_issue_key,))
            pre_public = pg_hook.get_first("SELECT key_id, created, updated, resolved FROM issues WHERE key_id = %s", parameters=(debug_issue_key,))
            logging.info(f"DEBUG PRE raw: {pre_raw} public: {pre_public}")
        except Exception as e:
            logging.warning(f"DEBUG PRE select failed: {e}")

    sql = f"""
    INSERT INTO statuses (id, project_id, name, status_id, category)
    SELECT DISTINCT 
        gen_random_uuid() as id,
        p.id as project_id,
        ps.name as name,
        ps.id as status_id,
        COALESCE({category_column}, 'To Do') as category
    FROM raw_jira.project_statuses__raw_data__statuses ps
    CROSS JOIN projects p
    {where_projects}
    ON CONFLICT (project_id, name) DO NOTHING;
    """
    
    pg_hook.run(sql, parameters=tuple(params) if params else None)
    logging.info("Statuses loaded successfully")

# @anchor:dag:load_issue_types
def load_issue_types(**kwargs):
    """Загружает типы задач из raw_jira в таблицу issue_types"""
    pg_hook = PostgresHook(postgres_conn_id='postgres_default')
    
    conf = _get_conf(kwargs)
    # disable debug_issue_key to avoid NameError and noisy debug prints
    debug_issue_key = None
    filter_keys = conf.get('project_keys') if isinstance(conf, dict) else None
    user_id = conf.get('user_id') if isinstance(conf, dict) else None
    integration_uuid = conf.get('integration_uuid') if isinstance(conf, dict) else None
    if filter_keys and not isinstance(filter_keys, list):
        filter_keys = [filter_keys]

    where_join = ""
    params = []
    if filter_keys:
        # Если пришли UUID'ы — считаем, что это project_id, а не external_key
        if all(_looks_like_uuid(k) for k in filter_keys):
            placeholders = ','.join(['%s'] * len(filter_keys))
            where_join += f" AND p.id IN ({placeholders})"
        else:
            placeholders = ','.join(['%s'] * len(filter_keys))
            where_join += f" AND p.external_key IN ({placeholders})"
        params.extend(filter_keys)
    if user_id and _looks_like_uuid(user_id):
        where_join += " AND p.user_id = %s::uuid"
        params.append(user_id)
    if integration_uuid and _looks_like_uuid(integration_uuid):
        where_join += " AND p.tool_integration_id = %s::uuid"
        params.append(integration_uuid)

    sql = f"""
    INSERT INTO issue_types (id, project_id, name, description, external_id)
    SELECT DISTINCT 
        gen_random_uuid() as id,
        p.id as project_id,
        i.issue_type as name,
        NULL as description,
        i.issue_type_id as external_id
    FROM raw_jira.issues i
    JOIN projects p ON p.external_key = SPLIT_PART(i.issue_key, '-', 1)
      {where_join}
    WHERE i.issue_type IS NOT NULL
    ON CONFLICT (project_id, name) DO NOTHING;
    """
    
    pg_hook.run(sql, parameters=tuple(params) if params else None)
    logging.info("Issue types loaded successfully")

# @anchor:dag:load_iteration_types
def load_iteration_types(**kwargs):
    """Загружает типы итераций из raw_jira в таблицу iteration_types (совместимо с обеими схемами)"""
    pg_hook = PostgresHook(postgres_conn_id='postgres_default')

    conf = _get_conf(kwargs)
    filter_keys = conf.get('project_keys') if isinstance(conf, dict) else None
    user_id = conf.get('user_id') if isinstance(conf, dict) else None
    integration_uuid = conf.get('integration_uuid') if isinstance(conf, dict) else None
    if filter_keys and not isinstance(filter_keys, list):
        filter_keys = [filter_keys]

    # Build filtered projects once via CTE to avoid duplicating parameters across UNION parts
    proj_filter_clause = "WHERE 1=1"
    params: list = []
    if filter_keys:
        placeholders = ','.join(['%s'] * len(filter_keys))
        if all(_looks_like_uuid(k) for k in filter_keys):
            proj_filter_clause += f" AND id IN ({placeholders})"
        else:
            proj_filter_clause += f" AND external_key IN ({placeholders})"
        params.extend(filter_keys)
    if user_id and _looks_like_uuid(user_id):
        proj_filter_clause += " AND user_id = %s::uuid"
        params.append(user_id)
    if integration_uuid and _looks_like_uuid(integration_uuid):
        proj_filter_clause += " AND tool_integration_id = %s::uuid"
        params.append(integration_uuid)

    # If current schema has per-project iteration types with external ids
    if _has_columns(pg_hook, 'public', 'iteration_types', ['project_id', 'external_id', 'external_name']):
        sql = f"""
        WITH pf AS (
            SELECT id, external_key FROM projects {proj_filter_clause}
        )
        INSERT INTO iteration_types (id, name, description, project_id, external_id, external_name)
        SELECT DISTINCT 
            gen_random_uuid() as id,
            'Sprint' as name,
            'Jira Sprint' as description,
            p.id as project_id,
            'sprint' as external_id,
            'Sprint' as external_name
        FROM raw_jira.sprints s
        JOIN projects p ON p.external_key = s.project_key
        JOIN pf ON pf.id = p.id
        WHERE s.sprint_id IS NOT NULL
        UNION
        SELECT DISTINCT 
            gen_random_uuid() as id,
            'Release' as name,
            'Jira Release' as description,
            p.id as project_id,
            'release' as external_id,
            'Release' as external_name
        FROM raw_jira.projects__raw_data__versions v
        JOIN projects p ON p.external_key = (SELECT project_key FROM raw_jira.projects WHERE project_id = v.project_id::varchar)
        JOIN pf ON pf.id = p.id
        WHERE v.id IS NOT NULL
        ON CONFLICT (project_id, name, external_id) DO NOTHING;
        """
        pg_hook.run(sql, parameters=tuple(params) if params else None)
    else:
        # Fallback minimal insert for schema variant without project/external columns
        sql_min = """
        INSERT INTO iteration_types (id, name, description)
        VALUES 
            (gen_random_uuid(), 'Sprint',  'Jira Sprint'),
            (gen_random_uuid(), 'Release', 'Jira Release')
        ON CONFLICT DO NOTHING;
        """
        pg_hook.run(sql_min)

    # minimal volume check
    cnt = pg_hook.get_first("SELECT COUNT(*) FROM iteration_types;")[0]
    if cnt == 0:
        raise Exception("iteration_types is empty after load")
    logging.info("Iteration types loaded successfully")

# @anchor:dag:load_iteration_statuses
def load_iteration_statuses(**kwargs):
    """Загружает статусы итераций из raw_jira в таблицу iteration_statuses (совместимо со схемой)"""
    pg_hook = PostgresHook(postgres_conn_id='postgres_default')

    conf = _get_conf(kwargs)
    filter_keys = conf.get('project_keys') if isinstance(conf, dict) else None
    user_id = conf.get('user_id') if isinstance(conf, dict) else None
    integration_uuid = conf.get('integration_uuid') if isinstance(conf, dict) else None
    if filter_keys and not isinstance(filter_keys, list):
        filter_keys = [filter_keys]

    # Use CTE for project filtering to avoid parameter duplication across UNION
    proj_filter_clause = "WHERE 1=1"
    params: list = []
    if filter_keys:
        placeholders = ','.join(['%s'] * len(filter_keys))
        if all(_looks_like_uuid(k) for k in filter_keys):
            proj_filter_clause += f" AND id IN ({placeholders})"
        else:
            proj_filter_clause += f" AND external_key IN ({placeholders})"
        params.extend(filter_keys)
    if user_id and _looks_like_uuid(user_id):
        proj_filter_clause += " AND user_id = %s::uuid"
        params.append(user_id)
    if integration_uuid and _looks_like_uuid(integration_uuid):
        proj_filter_clause += " AND tool_integration_id = %s::uuid"
        params.append(integration_uuid)

    if _has_columns(pg_hook, 'public', 'iteration_types', ['project_id']):
        sql = f"""
        WITH pf AS (
          SELECT id, external_key FROM projects {proj_filter_clause}
        )
        INSERT INTO iteration_statuses (id, name, iteration_type_id, description)
        SELECT DISTINCT 
            gen_random_uuid() as id,
            s.sprint_state as name,
            it.id as iteration_type_id,
            'Sprint ' || s.sprint_state as description
        FROM raw_jira.sprints s
        JOIN projects p ON p.external_key = s.project_key
        JOIN pf ON pf.id = p.id
        JOIN iteration_types it ON it.project_id = p.id AND it.name = 'Sprint'
        WHERE s.sprint_state IS NOT NULL
        UNION
        SELECT DISTINCT 
            gen_random_uuid() as id,
            CASE 
                WHEN v.released = true THEN 'Released'
                WHEN v.archived = true THEN 'Archived'
                ELSE 'Active'
            END as name,
            it.id as iteration_type_id,
            CASE 
                WHEN v.released = true THEN 'Released Release'
                WHEN v.archived = true THEN 'Archived Release'
                ELSE 'Active Release'
            END as description
        FROM raw_jira.projects__raw_data__versions v
        JOIN projects p ON p.external_key = (SELECT project_key FROM raw_jira.projects WHERE project_id = v.project_id::varchar)
        JOIN pf ON pf.id = p.id
        JOIN iteration_types it ON it.project_id = p.id AND it.name = 'Release'
        WHERE v.id IS NOT NULL
        ON CONFLICT (iteration_type_id, name) DO NOTHING;
        """
        pg_hook.run(sql, parameters=tuple(params) if params else None)
    else:
        # Fallback: bind statuses to global iteration types by name only
        sql_fallback = """
        INSERT INTO iteration_statuses (id, name, iteration_type_id, description)
        SELECT gen_random_uuid(), s, it.id, 'Sprint ' || s
        FROM (VALUES ('active'),('future'),('closed')) v(s)
        JOIN iteration_types it ON it.name = 'Sprint'
        ON CONFLICT (iteration_type_id, name) DO NOTHING;

        INSERT INTO iteration_statuses (id, name, iteration_type_id, description)
        SELECT gen_random_uuid(), s, it.id, 'Release ' || s
        FROM (VALUES ('Active'),('Released'),('Archived')) v(s)
        JOIN iteration_types it ON it.name = 'Release'
        ON CONFLICT (iteration_type_id, name) DO NOTHING;
        """
        pg_hook.run(sql_fallback)

    logging.info("Iteration statuses loaded successfully")

# @anchor:dag:load_custom_fields
def load_custom_fields(**kwargs):
    """Загружает кастомные поля из raw_jira в таблицу custom_fields"""
    pg_hook = PostgresHook(postgres_conn_id='postgres_default')

    conf = _get_conf(kwargs)
    filter_keys = conf.get('project_keys') if isinstance(conf, dict) else None
    user_id = conf.get('user_id') if isinstance(conf, dict) else None
    integration_uuid = conf.get('integration_uuid') if isinstance(conf, dict) else None
    if filter_keys and not isinstance(filter_keys, list):
        filter_keys = [filter_keys]

    # Получаем список всех таблиц issues__raw_data__fields__customfield_*
    # Ограничим загрузку только нужными полями, если заданы в переменной окружения или параметрах
    CUSTOM_FIELDS_FILTER = [
        'customfield_11041','customfield_10020','customfield_10000','customfield_10325',
        'customfield_11039','customfield_10019','customfield_10036','customfield_10253',
        'customfield_10254','customfield_10496','customfield_10498','customfield_10499','customfield_10201',
        'customfield_10016',  # Story point estimate
        'customfield_10036',  # Story Points  
        'customfield_10940'   # Story point пуст
    ]

    sql_get_tables = """
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'raw_jira' 
    AND table_name LIKE 'issues__raw_data__fields__customfield_%'
    AND table_name NOT LIKE '%content%'
    AND table_name NOT LIKE '%marks%'
    AND table_name NOT LIKE '%attrs%'
    """
    
    tables = pg_hook.get_records(sql_get_tables)
    logging.info(f"Found {len(tables)} custom field tables: {[t[0] for t in tables]}")
    
    if len(tables) == 0:
        # Проверим, какие таблицы вообще есть в raw_jira
        all_tables_sql = """
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'raw_jira' 
        ORDER BY table_name
        """
        all_tables = pg_hook.get_records(all_tables_sql)
        logging.info(f"All tables in raw_jira: {[t[0] for t in all_tables]}")
        return
    
    for table_record in tables:
        table_name = table_record[0]
        field_id = table_name.replace('issues__raw_data__fields__', '')

        # Если хотим фильтровать только по нужным полям (опционально)
        # if CUSTOM_FIELDS_FILTER and field_id not in CUSTOM_FIELDS_FILTER:
        #     continue
        
        # Получаем реальное имя поля из Jira API metadata или используем field_id как fallback
        # Сначала пытаемся получить человеческое имя из метаданных
        get_field_name_sql = f"""
        SELECT name 
        FROM raw_jira.fields 
        WHERE id = '{field_id}' 
        LIMIT 1;
        """
        
        try:
            field_name_result = pg_hook.get_first(get_field_name_sql)
            field_display_name = field_name_result[0] if field_name_result and field_name_result[0] else field_id
            logging.info(f"Found field name for {field_id}: {field_display_name}")
        except Exception as e:
            field_display_name = field_id
            logging.warning(f"Could not get field name for {field_id}, using ID as fallback: {e}")
        
        # Извлекаем информацию о кастомном поле из таблицы
        where_proj = ""
        params = []
        if filter_keys:
            placeholders = ','.join(['%s'] * len(filter_keys))
            if all(_looks_like_uuid(k) for k in filter_keys):
                where_proj += f" AND p.id IN ({placeholders})"
            else:
                where_proj += f" AND p.external_key IN ({placeholders})"
            params.extend(filter_keys)
        if user_id and _looks_like_uuid(user_id):
            where_proj += " AND p.user_id = %s::uuid"
            params.append(user_id)
        if integration_uuid and _looks_like_uuid(integration_uuid):
            where_proj += " AND p.tool_integration_id = %s::uuid"
            params.append(integration_uuid)

        sql = f"""
        INSERT INTO custom_fields (id, project_id, name, external_key, description)
        SELECT DISTINCT 
            gen_random_uuid() as id,
            p.id as project_id,
            '{field_display_name}' as name,
            '{field_id}' as external_key,
            'Custom field from {table_name}' as description
        FROM projects p
        WHERE p.external_key IN (
            SELECT DISTINCT raw_data__fields__project__key 
            FROM raw_jira.issues 
            WHERE issue_key IN (
                SELECT DISTINCT issue_key 
                FROM raw_jira.{table_name} 
                WHERE issue_key IS NOT NULL
            )
        ){where_proj}
        ON CONFLICT (project_id, external_key) DO UPDATE SET
            name = EXCLUDED.name,
            description = EXCLUDED.description;
        """
        
        try:
            pg_hook.run(sql, parameters=tuple(params) if params else None)
            logging.info(f"Loaded custom field: {field_id} from table {table_name}")
        except Exception as e:
            logging.error(f"Error loading custom field {field_id} from {table_name}: {e}")
    
    logging.info("Custom fields loading completed")

    # Дополнительно: добиваем кастомные поля по метаданным raw_jira.fields и JSON поля issues.raw_data->'fields'
    # Это покрывает случаи, когда DLT не создал отдельную таблицу issues__raw_data__fields__customfield_*
    try:
        where_proj2 = ""
        params2 = []
        if filter_keys:
            placeholders = ','.join(['%s'] * len(filter_keys))
            if all(_looks_like_uuid(k) for k in filter_keys):
                where_proj2 += f" AND p.id IN ({placeholders})"
            else:
                where_proj2 += f" AND p.external_key IN ({placeholders})"
            params2.extend(filter_keys)
        if user_id and _looks_like_uuid(user_id):
            where_proj2 += " AND p.user_id = %s::uuid"
            params2.append(user_id)
        if integration_uuid and _looks_like_uuid(integration_uuid):
            where_proj2 += " AND p.tool_integration_id = %s::uuid"
            params2.append(integration_uuid)

        sql_from_metadata = f"""
        INSERT INTO custom_fields (id, project_id, name, external_key, description)
        SELECT DISTINCT
            gen_random_uuid() as id,
            p.id as project_id,
            f.name as name,
            f.id as external_key,
            'Custom field from Jira fields metadata' as description
        FROM raw_jira.fields f
        JOIN raw_jira.issues iss ON (iss.raw_data->'fields') ? f.id
        JOIN projects p ON p.external_key = SPLIT_PART(iss.issue_key, '-', 1)
        WHERE f.id LIKE 'customfield_%'
          -- AND f.id = ANY(ARRAY{CUSTOM_FIELDS_FILTER})  -- Убираем фильтр, загружаем все поля
          {where_proj2}
        ON CONFLICT (project_id, external_key) DO UPDATE SET
            name = EXCLUDED.name,
            description = EXCLUDED.description;
        """
        pg_hook.run(sql_from_metadata, parameters=tuple(params2) if params2 else None)
        logging.info("Custom fields metadata backfill completed")
    except Exception as e:
        logging.warning(f"Custom fields metadata backfill failed: {e}")

    # Создадим недостающие custom_fields на основании changelog (чтобы values могло их использовать)
    try:
        where_proj3 = ""
        params3 = []
        if filter_keys:
            placeholders = ','.join(['%s'] * len(filter_keys))
            if all(_looks_like_uuid(k) for k in filter_keys):
                where_proj3 += f" AND p.id IN ({placeholders})"
            else:
                where_proj3 += f" AND p.external_key IN ({placeholders})"
            params3.extend(filter_keys)
        if user_id and _looks_like_uuid(user_id):
            where_proj3 += " AND p.user_id = %s::uuid"
            params3.append(user_id)
        if integration_uuid and _looks_like_uuid(integration_uuid):
            where_proj3 += " AND p.tool_integration_id = %s::uuid"
            params3.append(integration_uuid)

        sql_create_from_changelog = f"""
        INSERT INTO custom_fields (id, project_id, name, external_key, description)
        SELECT DISTINCT
            gen_random_uuid() as id,
            p.id as project_id,
            COALESCE(c.field_id, c.field) as name,
            COALESCE(c.field_id, c.field) as external_key,
            'Custom field from changelog' as description
        FROM raw_jira.changelog c
        JOIN raw_jira.issues ri ON ri.issue_key = c.issue_key
        JOIN projects p ON p.external_key = SPLIT_PART(ri.issue_key, '-', 1)
        WHERE COALESCE(c.field_id, c.field) LIKE 'customfield_%'
        AND NOT EXISTS (
            SELECT 1 FROM custom_fields cf 
            WHERE cf.external_key = COALESCE(c.field_id, c.field) AND cf.project_id = p.id
        ) {where_proj3}
        ON CONFLICT (project_id, external_key) DO NOTHING;
        """
        pg_hook.run(sql_create_from_changelog, parameters=tuple(params3) if params3 else None)
        logging.info("Created missing custom fields from changelog (pre-values)")
    except Exception as e:
        logging.warning(f"Failed to create custom fields from changelog: {e}")

    # Обновим human-readable name из raw_jira.fields, если нашли соответствие
    try:
        sql_update_names = """
        UPDATE custom_fields cf
        SET name = f.name,
            description = COALESCE(f.description, cf.description)
        FROM raw_jira.fields f
        WHERE cf.external_key = f.id
          AND f.name IS NOT NULL;
        """
        pg_hook.run(sql_update_names)
        logging.info("Updated custom_fields names from raw_jira.fields where available (unconditional)")
    except Exception as e:
        logging.warning(f"Failed to update custom_fields names: {e}")

    # Дополнительно: обновим имя поля по наиболее частому 'field' в changelog если оно человекочитаемое
    try:
        sql_update_from_changelog = """
        WITH names AS (
            SELECT COALESCE(field_id, field) as external_key,
                   field as candidate_name,
                   COUNT(*) as cnt
            FROM raw_jira.changelog
            WHERE COALESCE(field_id, field) LIKE 'customfield_%'
              AND field IS NOT NULL
              AND field NOT LIKE 'customfield_%'
            GROUP BY 1,2
        ), best AS (
            SELECT DISTINCT ON (external_key) external_key, candidate_name
            FROM names
            ORDER BY external_key, cnt DESC
        )
        UPDATE custom_fields cf
        SET name = b.candidate_name
        FROM best b
        WHERE cf.external_key = b.external_key
          AND (cf.name = cf.external_key OR cf.name LIKE 'customfield_%' OR cf.description ILIKE 'Custom field from changelog%');
        """
        pg_hook.run(sql_update_from_changelog)
        logging.info("Updated custom_fields names from changelog where fields metadata missing")
    except Exception as e:
        logging.warning(f"Failed to update custom_fields names from changelog: {e}")


# @anchor:dag:load_iterations
def load_iterations(**kwargs):
    """Загружает итерации из raw_jira в таблицу iterations"""
    pg_hook = PostgresHook(postgres_conn_id='postgres_default')
    
    conf = _get_conf(kwargs)
    filter_keys = conf.get('project_keys') if isinstance(conf, dict) else None
    user_id = conf.get('user_id') if isinstance(conf, dict) else None
    integration_uuid = conf.get('integration_uuid') if isinstance(conf, dict) else None
    if filter_keys and not isinstance(filter_keys, list):
        filter_keys = [filter_keys]

    # Build filtered projects once via CTE to reuse params across UNION
    proj_filter_clause = "WHERE 1=1"
    params: list = []
    if filter_keys:
        placeholders = ','.join(['%s'] * len(filter_keys))
        if all(_looks_like_uuid(k) for k in filter_keys):
            proj_filter_clause += f" AND id IN ({placeholders})"
        else:
            proj_filter_clause += f" AND external_key IN ({placeholders})"
        params.extend(filter_keys)
    if user_id and _looks_like_uuid(user_id):
        proj_filter_clause += " AND user_id = %s::uuid"
        params.append(user_id)
    if integration_uuid and _looks_like_uuid(integration_uuid):
        proj_filter_clause += " AND tool_integration_id = %s::uuid"
        params.append(integration_uuid)

    sql = f"""
    WITH pf AS (
        SELECT id, external_key FROM projects {proj_filter_clause}
    )
    INSERT INTO iterations (
        id, project_id, name, start_date, end_date, complete_date,
        iteration_type_id, iteration_status_id, external_id
    )
    SELECT DISTINCT 
        gen_random_uuid() as id,
        p.id as project_id,
        s.sprint_name as name,
        s.sprint_start_date as start_date,
        s.sprint_end_date as end_date,
        CASE WHEN s.sprint_state = 'closed' THEN s.sprint_complete_date ELSE NULL END as complete_date,
        it.id as iteration_type_id,
        (SELECT id FROM iteration_statuses WHERE name = s.sprint_state AND iteration_type_id = it.id) as iteration_status_id,
        s.sprint_id::varchar as external_id
    FROM raw_jira.sprints s
    JOIN projects p ON p.external_key = s.project_key
    JOIN pf ON pf.id = p.id
    JOIN iteration_types it ON it.project_id = p.id AND it.name = 'Sprint'
    WHERE s.sprint_id IS NOT NULL
    UNION
    SELECT DISTINCT 
        gen_random_uuid() as id,
        p.id as project_id,
        v.name as name,
        CASE 
            WHEN v.start_date IS NOT NULL AND v.start_date != '' THEN v.start_date::date
            ELSE v.release_date::date
        END as start_date,
        CASE 
            WHEN v.release_date IS NOT NULL AND v.release_date != '' THEN v.release_date::date
            ELSE v.start_date::date
        END as end_date,
        CASE 
            WHEN v.release_date IS NOT NULL AND v.release_date != '' THEN v.release_date::timestamptz
            ELSE NULL
        END as complete_date,
        it.id as iteration_type_id,
        (SELECT id FROM iteration_statuses WHERE name = 
            CASE 
                WHEN v.released = true THEN 'Released'
                WHEN v.archived = true THEN 'Archived'
                ELSE 'Active'
            END 
            AND iteration_type_id = it.id) as iteration_status_id,
        v.id::varchar as external_id
    FROM raw_jira.projects__raw_data__versions v
    JOIN projects p ON p.external_key = (SELECT project_key FROM raw_jira.projects WHERE project_id = v.project_id::varchar)
    JOIN pf ON pf.id = p.id
    JOIN iteration_types it ON it.project_id = p.id AND it.name = 'Release'
    WHERE v.id IS NOT NULL
    ON CONFLICT (project_id, external_id) DO UPDATE SET
        name = EXCLUDED.name,
        start_date = EXCLUDED.start_date,
        end_date = EXCLUDED.end_date,
        complete_date = EXCLUDED.complete_date,
        iteration_status_id = EXCLUDED.iteration_status_id;
    """
    
    pg_hook.run(sql, parameters=tuple(params) if params else None)
    logging.info("Iterations loaded successfully")


# @anchor:dag:load_boards
def load_boards(**kwargs):
    """Load boards list from raw_jira.board_config into public.boards"""
    pg = PostgresHook(postgres_conn_id='postgres_default')

    conf = _get_conf(kwargs)
    filter_keys = conf.get('project_keys') if isinstance(conf, dict) else None
    if filter_keys and not isinstance(filter_keys, list):
        filter_keys = [filter_keys]

    proj_where = "WHERE 1=1"
    params = []
    if filter_keys:
        placeholders = ','.join(['%s'] * len(filter_keys))
        if all(_looks_like_uuid(k) for k in filter_keys):
            proj_where += f" AND id IN ({placeholders})"
        else:
            proj_where += f" AND external_key IN ({placeholders})"
        params.extend(filter_keys)

    # If raw JSON exists -> use it; else fall back to flattened columns; else try raw_jira.boards
    if _has_columns(pg, 'raw_jira', 'board_config', ['raw_data']):
        sql = f"""
        WITH pf AS (
          SELECT id, external_key FROM projects {proj_where}
        )
        INSERT INTO boards (id, project_id, board_id, name, type)
        SELECT DISTINCT
          gen_random_uuid() as id,
          p.id as project_id,
          (bc.raw_data->>'id')::text as board_id,
          bc.raw_data->>'name' as name,
          bc.raw_data->>'type' as type
        FROM raw_jira.board_config bc
        JOIN projects p ON p.external_key = bc.project_key
        JOIN pf ON pf.id = p.id
        WHERE bc.raw_data IS NOT NULL
        ON CONFLICT (project_id, board_id) DO UPDATE SET
          name = EXCLUDED.name,
          type = EXCLUDED.type;
        """
        pg.run(sql, parameters=tuple(params) if params else None)
    elif _has_columns(pg, 'raw_jira', 'board_config', ['board_id', 'board_name', 'board_type', 'project_key']):
        sql_flat = f"""
        WITH pf AS (
          SELECT id, external_key FROM projects {proj_where}
        )
        INSERT INTO boards (id, project_id, board_id, name, type)
        SELECT DISTINCT
          gen_random_uuid() as id,
          p.id as project_id,
          bc.board_id::text as board_id,
          bc.board_name as name,
          bc.board_type as type
        FROM raw_jira.board_config bc
        JOIN projects p ON p.external_key = bc.project_key
        JOIN pf ON pf.id = p.id
        ON CONFLICT (project_id, board_id) DO UPDATE SET
          name = EXCLUDED.name,
          type = EXCLUDED.type;
        """
        pg.run(sql_flat, parameters=tuple(params) if params else None)
    elif _table_exists(pg, 'raw_jira', 'boards') and _has_columns(pg, 'raw_jira', 'boards', ['board_id', 'board_name', 'board_type', 'project_key']):
        sql_boards = f"""
        WITH pf AS (
          SELECT id, external_key FROM projects {proj_where}
        )
        INSERT INTO boards (id, project_id, board_id, name, type)
        SELECT DISTINCT
          gen_random_uuid() as id,
          p.id as project_id,
          b.board_id::text as board_id,
          b.board_name as name,
          b.board_type as type
        FROM raw_jira.boards b
        JOIN projects p ON p.external_key = b.project_key
        JOIN pf ON pf.id = p.id
        ON CONFLICT (project_id, board_id) DO UPDATE SET
          name = EXCLUDED.name,
          type = EXCLUDED.type;
        """
        pg.run(sql_boards, parameters=tuple(params) if params else None)
    else:
        logging.warning("No suitable sources for boards found in raw_jira; skipping load_boards")
    logging.info("Boards loaded successfully")


# @anchor:dag:load_board_columns
def load_board_columns(**kwargs):
    """Extract board columns (name, order) from raw_jira.board_config -> columnConfig.columns"""
    pg = PostgresHook(postgres_conn_id='postgres_default')
    conf = _get_conf(kwargs)
    filter_keys = conf.get('project_keys') if isinstance(conf, dict) else None
    if filter_keys and not isinstance(filter_keys, list):
        filter_keys = [filter_keys]

    proj_where = "WHERE 1=1"
    params = []
    if filter_keys:
        placeholders = ','.join(['%s'] * len(filter_keys))
        if all(_looks_like_uuid(k) for k in filter_keys):
            proj_where += f" AND id IN ({placeholders})"
        else:
            proj_where += f" AND external_key IN ({placeholders})"
        params.extend(filter_keys)

    # If raw JSON column doesn't exist (DLT flattened nested structures), skip
    if not _has_columns(pg, 'raw_jira', 'board_config', ['raw_data']):
        logging.info("raw_jira.board_config.raw_data column not found; attempting to load from DLT-generated child tables")

        # Find child table that contains columns list (DLT naming pattern)
        tbl_row = pg.get_first("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'raw_jira' AND table_name ILIKE 'board_config__raw_data__%columns%'
            ORDER BY table_name LIMIT 1
        """)
        if not tbl_row:
            logging.warning("No child table for board_config.columns found in raw_jira; skipping load_board_columns")
            return
        cols_tbl = tbl_row[0]

        # Determine column name for column display (fallbacks)
        name_col = None
        for candidate in ('name', 'raw_data__name', 'col_name'):
            exists = pg.get_first("SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='raw_jira' AND table_name=%s AND column_name=%s)", parameters=(cols_tbl, candidate))
            if exists and exists[0]:
                name_col = candidate
                break
        if not name_col:
            logging.warning(f"Child table {cols_tbl} does not have expected name column; skipping")
            return

        # Insert board columns from child table joining to parent board_config via _dlt_parent_id
        sql_child = f'''
        WITH dedup AS (
          SELECT b.id AS board_id, c.{name_col}::text AS name, MIN(c._dlt_list_idx::int) AS order_num
          FROM raw_jira."{cols_tbl}" c
          JOIN raw_jira.board_config p ON p._dlt_id = c._dlt_parent_id
          JOIN projects pr ON pr.external_key = p.project_key
          JOIN boards b ON b.project_id = pr.id AND b.board_id = p.board_id::text
          GROUP BY b.id, c.{name_col}::text
        )
        INSERT INTO board_columns (id, board_id, name, order_num)
        SELECT gen_random_uuid(), board_id, name, order_num FROM dedup
        ON CONFLICT (board_id, name) DO NOTHING;
        '''
        pg.run(sql_child)
        logging.info("Board columns loaded successfully from child table %s", cols_tbl)
        return

    sql = f"""
    WITH pf AS (
      SELECT id, external_key FROM projects {proj_where}
    ), cfgs AS (
      SELECT project_key, raw_data, (raw_data->>'id')::text AS board_ext_id
      FROM raw_jira.board_config
      WHERE raw_data IS NOT NULL
    ), cols AS (
      SELECT c.project_key, c.board_ext_id, col.elem as col_json, col.ordinality as order_num
      FROM cfgs c
      CROSS JOIN LATERAL jsonb_array_elements(c.raw_data->'columnConfig'->'columns') WITH ORDINALITY AS col(elem, ordinality)
    )
    INSERT INTO board_columns (id, board_id, name, order_num)
    WITH dedup_cols AS (
      SELECT b.id AS board_id, (col_json->>'name')::text AS name, MIN(order_num) AS order_num
      FROM cols
      JOIN projects p ON p.external_key = cols.project_key
      JOIN boards b ON b.project_id = p.id AND b.board_id = cols.board_ext_id
      GROUP BY b.id, (col_json->>'name')::text
    )
    INSERT INTO board_columns (id, board_id, name, order_num)
    SELECT gen_random_uuid(), board_id, name, order_num FROM dedup_cols
    ON CONFLICT (board_id, name) DO NOTHING;
    """

    pg.run(sql, parameters=tuple(params) if params else None)
    logging.info("Board columns loaded successfully")


# @anchor:dag:load_board_column_statuses
def load_board_column_statuses(**kwargs):
    """Extract mapping column -> statuses from raw_jira.board_config into board_column_statuses"""
    pg = PostgresHook(postgres_conn_id='postgres_default')
    conf = _get_conf(kwargs)
    filter_keys = conf.get('project_keys') if isinstance(conf, dict) else None
    if filter_keys and not isinstance(filter_keys, list):
        filter_keys = [filter_keys]

    proj_where = "WHERE 1=1"
    params = []
    if filter_keys:
        placeholders = ','.join(['%s'] * len(filter_keys))
        if all(_looks_like_uuid(k) for k in filter_keys):
            proj_where += f" AND id IN ({placeholders})"
        else:
            proj_where += f" AND external_key IN ({placeholders})"
        params.extend(filter_keys)

    # If raw JSON column doesn't exist, skip
    if not _has_columns(pg, 'raw_jira', 'board_config', ['raw_data']):
        logging.info("raw_jira.board_config.raw_data column not found; attempting to load statuses from DLT-generated child tables")

        # Find child table for columns and statuses
        cols_row = pg.get_first("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'raw_jira' AND table_name ILIKE 'board_config__raw_data__%columns%'
            ORDER BY table_name LIMIT 1
        """)
        stats_row = pg.get_first("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'raw_jira' AND table_name ILIKE 'board_config__raw_data__%statuses%'
            ORDER BY table_name LIMIT 1
        """)
        if not cols_row or not stats_row:
            logging.warning("Could not find child tables for columns/statuses in raw_jira; skipping load_board_column_statuses")
            return
        cols_tbl = cols_row[0]
        stats_tbl = stats_row[0]

        # Determine status id column name candidate
        stat_id_col = None
        for candidate in ('id', 'raw_data__id', 'status_id'):
            exists = pg.get_first("SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='raw_jira' AND table_name=%s AND column_name=%s)", parameters=(stats_tbl, candidate))
            if exists and exists[0]:
                stat_id_col = candidate
                break
        if not stat_id_col:
            logging.warning(f"Status child table {stats_tbl} does not have expected id column; skipping")
            return

        # Build and run insertion SQL that joins statuses to columns via DLT parent ids
        sql_child = f'''
        INSERT INTO board_column_statuses (id, board_column_id, status_id)
        SELECT gen_random_uuid(), bc.id, st.id
        FROM raw_jira."{stats_tbl}" s
        JOIN raw_jira."{cols_tbl}" c ON c._dlt_id = s._dlt_parent_id
        JOIN raw_jira.board_config p ON p._dlt_id = c._dlt_parent_id
        JOIN projects pr ON pr.external_key = p.project_key
        JOIN boards b ON b.project_id = pr.id AND b.board_id = p.board_id::text
        JOIN board_columns bc ON bc.board_id = b.id AND bc.order_num = c._dlt_list_idx
        JOIN statuses st ON st.project_id = pr.id AND (st.status_id::text = s.{stat_id_col}::text OR st.status_id = s.{stat_id_col})
        ON CONFLICT DO NOTHING;
        '''
        pg.run(sql_child)
        logging.info("Board column statuses loaded successfully from child tables %s/%s", cols_tbl, stats_tbl)
        return

    sql = f"""
    WITH pf AS (
      SELECT id, external_key FROM projects {proj_where}
    ), cfgs AS (
      SELECT project_key, raw_data, (raw_data->>'id')::text AS board_ext_id
      FROM raw_jira.board_config
      WHERE raw_data IS NOT NULL
    ), cols AS (
      SELECT c.project_key, c.board_ext_id, col.elem as col_json, col.ordinality as order_num
      FROM cfgs c
      CROSS JOIN LATERAL jsonb_array_elements(c.raw_data->'columnConfig'->'columns') WITH ORDINALITY AS col(elem, ordinality)
    ), statuses_flat AS (
      SELECT cols.project_key, cols.board_ext_id, cols.order_num, stat.elem->>'id' AS status_ext_id
      FROM cols
      CROSS JOIN LATERAL jsonb_array_elements(cols.col_json->'statuses') AS stat(elem)
    )
    INSERT INTO board_column_statuses (id, board_column_id, status_id)
    SELECT gen_random_uuid(), bc.id, s.id
    FROM statuses_flat sf
    JOIN projects p ON p.external_key = sf.project_key
    JOIN boards b ON b.project_id = p.id AND b.board_id = sf.board_ext_id
    JOIN board_columns bc ON bc.board_id = b.id AND bc.order_num = sf.order_num
    JOIN statuses s ON s.project_id = p.id AND s.status_id = sf.status_ext_id
    ON CONFLICT DO NOTHING;
    """

    pg.run(sql, parameters=tuple(params) if params else None)
    logging.info("Board column statuses loaded successfully")

# @anchor:dag:load_issues
def load_issues(**kwargs):
    """Загружает задачи из raw_jira в таблицу issues"""
    pg_hook = PostgresHook(postgres_conn_id='postgres_default')
    
    # Проверяем количество задач в raw_jira.issues
    count_sql = "SELECT COUNT(*) FROM raw_jira.issues;"
    total_issues = pg_hook.get_first(count_sql)[0]
    logging.info(f"Total issues in raw_jira.issues: {total_issues}")
    
    # Проверяем количество проектов
    projects_sql = "SELECT COUNT(*) FROM projects;"
    total_projects = pg_hook.get_first(projects_sql)[0]
    logging.info(f"Total projects: {total_projects}")
    
    # Проверяем количество типов задач
    issue_types_sql = "SELECT COUNT(*) FROM issue_types;"
    total_issue_types = pg_hook.get_first(issue_types_sql)[0]
    logging.info(f"Total issue types: {total_issue_types}")
    
    # Проверяем количество статусов
    statuses_sql = "SELECT COUNT(*) FROM statuses;"
    total_statuses = pg_hook.get_first(statuses_sql)[0]
    logging.info(f"Total statuses: {total_statuses}")
    
    conf = _get_conf(kwargs)
    filter_keys = conf.get('project_keys') if isinstance(conf, dict) else None
    user_id = conf.get('user_id') if isinstance(conf, dict) else None
    integration_uuid = conf.get('integration_uuid') if isinstance(conf, dict) else None
    date_from = conf.get('date_from') if isinstance(conf, dict) else None
    date_to = conf.get('date_to') if isinstance(conf, dict) else None
    apply_filters = bool(conf.get('apply_filters')) if isinstance(conf, dict) else False
    if filter_keys and not isinstance(filter_keys, list):
        filter_keys = [filter_keys]

    extra_where = ""
    params = []
    if filter_keys:
        if all(_looks_like_uuid(k) for k in filter_keys):
            placeholders = ','.join(['%s'] * len(filter_keys))
            extra_where += f" AND p.id IN ({placeholders})"
        else:
            placeholders = ','.join(['%s'] * len(filter_keys))
            extra_where += f" AND p.external_key IN ({placeholders})"
        params.extend(filter_keys)
    # Apply optional filters only when explicitly enabled
    if apply_filters:
        if user_id and _looks_like_uuid(user_id):
            extra_where += " AND p.user_id = %s::uuid"
            params.append(user_id)
        if integration_uuid and _looks_like_uuid(integration_uuid):
            extra_where += " AND p.tool_integration_id = %s::uuid"
            params.append(integration_uuid)
        if date_from:
            # include issues that were created OR updated OR resolved in the window
            extra_where += (
                " AND (i.created >= %s::timestamptz OR i.updated >= %s::timestamptz "
                "OR (i.resolution_date IS NOT NULL AND i.resolution_date >= %s::timestamptz))"
            )
            params.extend([date_from, date_from, date_from])
        if date_to:
            extra_where += (
                " AND (i.created <= %s::timestamptz OR i.updated <= %s::timestamptz "
                "OR (i.resolution_date IS NOT NULL AND i.resolution_date <= %s::timestamptz))"
            )
            params.extend([date_to, date_to, date_to])

    # Diagnostics: log effective filters and row counts
    try:
        logging.info(f"load_issues params: project_keys={filter_keys}, user_id={user_id}, integration_uuid={integration_uuid}, date_from={date_from}, date_to={date_to}, apply_filters={apply_filters}")
        base_cnt = pg_hook.get_first(
            """
            SELECT COUNT(*)
            FROM raw_jira.issues i
            JOIN projects p ON p.external_key = SPLIT_PART(i.issue_key, '-', 1)
            WHERE i.issue_key IS NOT NULL
            """
        )[0]
        logging.info(f"load_issues base join count: {base_cnt}")
        if extra_where:
            cnt_with_filters = pg_hook.get_first(
                f"""
                SELECT COUNT(*)
                FROM raw_jira.issues i
                JOIN projects p ON p.external_key = SPLIT_PART(i.issue_key, '-', 1)
                WHERE i.issue_key IS NOT NULL {extra_where}
                """,
                parameters=tuple(params) if params else None,
            )[0]
            logging.info(f"load_issues after extra_where: {cnt_with_filters}")

        # Deep diagnostics: build a candidate scope and analyze matching quality
        diag_sql_scope = f"""
        WITH candidates AS (
          SELECT i.*, p.id AS project_id
          FROM raw_jira.issues i
          JOIN projects p ON p.external_key = SPLIT_PART(i.issue_key, '-', 1)
          WHERE i.issue_key IS NOT NULL {extra_where}
        )
        SELECT
          (SELECT COUNT(*) FROM candidates) AS total_candidates,
          (SELECT MIN(created) FROM candidates) AS min_created,
          (SELECT MAX(created) FROM candidates) AS max_created,
          (SELECT MIN(updated) FROM candidates) AS min_updated,
          (SELECT MAX(updated) FROM candidates) AS max_updated,
          (SELECT MAX(resolution_date) FROM candidates) AS max_resolved
        """
        tot_row = pg_hook.get_first(diag_sql_scope, parameters=tuple(params) if params else None)
        if tot_row:
            logging.info(
                "candidates: total=%s; min_created=%s; max_created=%s; min_updated=%s; max_updated=%s; max_resolved=%s",
                tot_row[0], tot_row[1], tot_row[2], tot_row[3], tot_row[4], tot_row[5]
            )

        # Match quality for issue_types (by id vs by name)
        diag_types_id = pg_hook.get_first(
            f"""
            WITH c AS (
              SELECT i.issue_type, i.issue_type_id, i.project_id FROM (
                SELECT i.*, p.id AS project_id
                FROM raw_jira.issues i JOIN projects p ON p.external_key = SPLIT_PART(i.issue_key,'-',1)
                WHERE i.issue_key IS NOT NULL {extra_where}
              ) i
            )
            SELECT COUNT(*)
            FROM c JOIN issue_types it
              ON it.project_id = c.project_id AND c.issue_type_id IS NOT NULL AND it.external_id = c.issue_type_id
            """,
            parameters=tuple(params) if params else None,
        )[0]
        diag_types_name = pg_hook.get_first(
            f"""
            WITH c AS (
              SELECT i.issue_type, i.issue_type_id, i.project_id FROM (
                SELECT i.*, p.id AS project_id
                FROM raw_jira.issues i JOIN projects p ON p.external_key = SPLIT_PART(i.issue_key,'-',1)
                WHERE i.issue_key IS NOT NULL {extra_where}
              ) i
            )
            SELECT COUNT(*)
            FROM c JOIN issue_types it
              ON it.project_id = c.project_id AND it.name = c.issue_type
            """,
            parameters=tuple(params) if params else None,
        )[0]
        diag_types_unmatched = pg_hook.get_first(
            f"""
            WITH c AS (
              SELECT i.issue_type, i.issue_type_id, i.project_id FROM (
                SELECT i.*, p.id AS project_id
                FROM raw_jira.issues i JOIN projects p ON p.external_key = SPLIT_PART(i.issue_key,'-',1)
                WHERE i.issue_key IS NOT NULL {extra_where}
              ) i
            )
            SELECT COUNT(*) FROM c
            LEFT JOIN issue_types it
              ON it.project_id = c.project_id AND (
                   (c.issue_type_id IS NOT NULL AND it.external_id = c.issue_type_id)
                OR (it.name = c.issue_type)
              )
            WHERE it.id IS NULL
            """,
            parameters=tuple(params) if params else None,
        )[0]
        logging.info(
            "issue_types match: by_id=%s, by_name=%s, unmatched=%s",
            diag_types_id, diag_types_name, diag_types_unmatched
        )
        try:
            top_unmatched_types = pg_hook.get_records(
                f"""
                WITH c AS (
                  SELECT i.issue_type, i.issue_type_id, i.project_id FROM (
                    SELECT i.*, p.id AS project_id
                    FROM raw_jira.issues i JOIN projects p ON p.external_key = SPLIT_PART(i.issue_key,'-',1)
                    WHERE i.issue_key IS NOT NULL {extra_where}
                  ) i
                )
                SELECT COALESCE(issue_type,'<NULL>') AS t_name, issue_type_id, COUNT(*) AS cnt
                FROM c LEFT JOIN issue_types it
                  ON it.project_id = c.project_id AND (
                       (c.issue_type_id IS NOT NULL AND it.external_id = c.issue_type_id)
                    OR (it.name = c.issue_type)
                  )
                WHERE it.id IS NULL
                GROUP BY 1,2
                ORDER BY cnt DESC
                LIMIT 10
                """,
                parameters=tuple(params) if params else None,
            )
            logging.info("top unmatched issue_types (name, id, cnt): %s", top_unmatched_types)
        except Exception:
            pass

        # Match quality for statuses (by id vs by name)
        diag_status_id = pg_hook.get_first(
            f"""
            WITH c AS (
              SELECT i.status, i.status_id, i.project_id FROM (
                SELECT i.*, p.id AS project_id
                FROM raw_jira.issues i JOIN projects p ON p.external_key = SPLIT_PART(i.issue_key,'-',1)
                WHERE i.issue_key IS NOT NULL {extra_where}
              ) i
            )
            SELECT COUNT(*)
            FROM c JOIN statuses s
              ON s.project_id = c.project_id AND c.status_id IS NOT NULL AND s.status_id = c.status_id
            """,
            parameters=tuple(params) if params else None,
        )[0]
        diag_status_name = pg_hook.get_first(
            f"""
            WITH c AS (
              SELECT i.status, i.status_id, i.project_id FROM (
                SELECT i.*, p.id AS project_id
                FROM raw_jira.issues i JOIN projects p ON p.external_key = SPLIT_PART(i.issue_key,'-',1)
                WHERE i.issue_key IS NOT NULL {extra_where}
              ) i
            )
            SELECT COUNT(*)
            FROM c JOIN statuses s
              ON s.project_id = c.project_id AND s.name = c.status
            """,
            parameters=tuple(params) if params else None,
        )[0]
        diag_status_unmatched = pg_hook.get_first(
            f"""
            WITH c AS (
              SELECT i.status, i.status_id, i.project_id FROM (
                SELECT i.*, p.id AS project_id
                FROM raw_jira.issues i JOIN projects p ON p.external_key = SPLIT_PART(i.issue_key,'-',1)
                WHERE i.issue_key IS NOT NULL {extra_where}
              ) i
            )
            SELECT COUNT(*) FROM c
            LEFT JOIN statuses s
              ON s.project_id = c.project_id AND (
                   (c.status_id IS NOT NULL AND s.status_id = c.status_id)
                OR (s.name = c.status)
              )
            WHERE s.id IS NULL
            """,
            parameters=tuple(params) if params else None,
        )[0]
        logging.info(
            "statuses match: by_id=%s, by_name=%s, unmatched=%s",
            diag_status_id, diag_status_name, diag_status_unmatched
        )
        try:
            top_unmatched_statuses = pg_hook.get_records(
                f"""
                WITH c AS (
                  SELECT i.status, i.status_id, i.project_id FROM (
                    SELECT i.*, p.id AS project_id
                    FROM raw_jira.issues i JOIN projects p ON p.external_key = SPLIT_PART(i.issue_key,'-',1)
                    WHERE i.issue_key IS NOT NULL {extra_where}
                  ) i
                )
                SELECT COALESCE(status,'<NULL>') AS s_name, status_id, COUNT(*) AS cnt
                FROM c LEFT JOIN statuses s
                  ON s.project_id = c.project_id AND (
                       (c.status_id IS NOT NULL AND s.status_id = c.status_id)
                    OR (s.name = c.status)
                  )
                WHERE s.id IS NULL
                GROUP BY 1,2
                ORDER BY cnt DESC
                LIMIT 10
                """,
                parameters=tuple(params) if params else None,
            )
            logging.info("top unmatched statuses (name, id, cnt): %s", top_unmatched_statuses)
        except Exception:
            pass
    except Exception as diag_e:
        logging.warning(f"load_issues diagnostics failed: {diag_e}")

    # Protective backfills: ensure missing issue_types and statuses exist for candidates before insert
    try:
        ensure_types_sql = f"""
        WITH c AS (
          SELECT DISTINCT p.id AS project_id, i.issue_type, i.issue_type_id
          FROM raw_jira.issues i
          JOIN projects p ON p.external_key = SPLIT_PART(i.issue_key, '-', 1)
          WHERE i.issue_key IS NOT NULL {extra_where}
        )
        INSERT INTO issue_types (id, project_id, name, description, external_id)
        SELECT gen_random_uuid(), project_id,
               COALESCE(issue_type, '<UNKNOWN>') AS name,
               NULL,
               issue_type_id
        FROM c
        WHERE NOT EXISTS (
          SELECT 1 FROM issue_types it
          WHERE it.project_id = c.project_id AND (
                (c.issue_type_id IS NOT NULL AND it.external_id = c.issue_type_id)
             OR (LOWER(it.name) = LOWER(c.issue_type))
          )
        )
        ON CONFLICT (project_id, name) DO NOTHING;
        """
        pg_hook.run(ensure_types_sql, parameters=tuple(params) if params else None)
        logging.info("Ensured missing issue_types for candidates")
    except Exception as e:
        logging.warning(f"Failed to ensure issue_types: {e}")

    try:
        ensure_statuses_sql = f"""
        WITH c AS (
          SELECT DISTINCT p.id AS project_id, i.status, i.status_id
          FROM raw_jira.issues i
          JOIN projects p ON p.external_key = SPLIT_PART(i.issue_key, '-', 1)
          WHERE i.issue_key IS NOT NULL {extra_where}
        )
        INSERT INTO statuses (id, project_id, name, status_id, category)
        SELECT gen_random_uuid(), project_id,
               COALESCE(status, '<UNKNOWN>') AS name,
               status_id,
               'To Do' AS category
        FROM c
        WHERE NOT EXISTS (
          SELECT 1 FROM statuses s
          WHERE s.project_id = c.project_id AND (
                (c.status_id IS NOT NULL AND s.status_id = c.status_id)
             OR (LOWER(s.name) = LOWER(c.status))
          )
        )
        ON CONFLICT (project_id, name) DO NOTHING;
        """
        pg_hook.run(ensure_statuses_sql, parameters=tuple(params) if params else None)
        logging.info("Ensured missing statuses for candidates")
    except Exception as e:
        logging.warning(f"Failed to ensure statuses: {e}")

    sql = f"""
    INSERT INTO issues (
        id, key_id, summary, type_id, current_status_id, created, updated, resolved, 
        assignee, reporter, project_id, estimate
    )
    SELECT DISTINCT 
        gen_random_uuid() as id,
        i.issue_key as key_id,
        i.summary,
        it.id as type_id,
        s.id as current_status_id,
        i.created as created,
        i.updated as updated,
        i.resolution_date as resolved,
        COALESCE(i.assignee, '') as assignee,
        COALESCE(i.reporter, '') as reporter,
        p.id as project_id,
        i.story_points as estimate
    FROM raw_jira.issues i
    JOIN projects p ON p.external_key = SPLIT_PART(i.issue_key, '-', 1)
    /* Prefer stable joins by external ids (when present), else fallback to names */
    LEFT JOIN issue_types it 
      ON it.project_id = p.id 
     AND (
          (i.issue_type_id IS NOT NULL AND it.external_id = i.issue_type_id)
          OR (LOWER(it.name) = LOWER(i.issue_type))
     )
    LEFT JOIN statuses s 
      ON s.project_id = p.id 
     AND (
          (i.status_id IS NOT NULL AND s.status_id = i.status_id)
          OR (LOWER(s.name) = LOWER(i.status))
     )
    WHERE i.issue_key IS NOT NULL {extra_where}
      AND it.id IS NOT NULL AND s.id IS NOT NULL
    ON CONFLICT (key_id, project_id) DO UPDATE SET
        summary = EXCLUDED.summary,
        type_id = EXCLUDED.type_id,
        current_status_id = EXCLUDED.current_status_id,
        updated = EXCLUDED.updated,
        resolved = EXCLUDED.resolved,
        assignee = EXCLUDED.assignee,
        reporter = EXCLUDED.reporter,
        estimate = EXCLUDED.estimate;
    """
    
    pg_hook.run(sql, parameters=tuple(params) if params else None)
    
    # Проверяем количество загруженных задач
    loaded_sql = "SELECT COUNT(*) FROM issues;"
    loaded_issues = pg_hook.get_first(loaded_sql)[0]
    logging.info(f"Issues loaded successfully: {loaded_issues}")
    if False:
        try:
            post_raw = pg_hook.get_first("SELECT issue_key, created, updated, resolution_date FROM raw_jira.issues WHERE issue_key = %s", parameters=(debug_issue_key,))
            post_public = pg_hook.get_first("SELECT key_id, created, updated, resolved FROM issues WHERE key_id = %s", parameters=(debug_issue_key,))
            logging.info(f"DEBUG POST raw: {post_raw} public: {post_public}")
        except Exception as e:
            logging.warning(f"DEBUG POST select failed: {e}")

# @anchor:dag:load_issue_iterations
def load_issue_iterations(**kwargs):
    """Загружает актуальные связи задач со спринтами/релизами на основе всей истории (со сплитом списков)"""
    pg_hook = PostgresHook(postgres_conn_id='postgres_default')
    
    # Проверяем, существует ли таблица changelog
    check_sql = """
    SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'raw_jira' 
        AND table_name = 'changelog'
    );
    """
    
    changelog_exists = pg_hook.get_first(check_sql)[0]
    
    if not changelog_exists:
        logging.warning("Table raw_jira.changelog does not exist, skipping issue iterations")
        return
    
    # Проверим количество записей в changelog
    count_sql = "SELECT COUNT(*) FROM raw_jira.changelog;"
    changelog_count = pg_hook.get_first(count_sql)[0]
    logging.info(f"Total records in raw_jira.changelog: {changelog_count}")
    
    # Проверим уникальные поля в changelog
    fields_sql = "SELECT DISTINCT field FROM raw_jira.changelog WHERE field IS NOT NULL;"
    fields = pg_hook.get_records(fields_sql)
    logging.info(f"Unique fields in changelog: {[f[0] for f in fields]}")
    
    # Проверим структуру таблицы raw_jira.issues
    issues_columns_sql = """
    SELECT column_name 
    FROM information_schema.columns 
    WHERE table_schema = 'raw_jira' 
    AND table_name = 'issues'
    ORDER BY ordinal_position
    """
    issues_columns = pg_hook.get_records(issues_columns_sql)
    logging.info(f"Columns in raw_jira.issues: {[col[0] for col in issues_columns]}")
    
    # Индексы для ускорения и уникальности
    pg_hook.run("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_issue_iterations_unique
        ON issue_iterations(issue_id, iteration_id);
    """)
    pg_hook.run("""
        CREATE INDEX IF NOT EXISTS idx_iterations_external_id ON iterations(external_id);
    """)
    pg_hook.run("""
        CREATE INDEX IF NOT EXISTS idx_issues_key_id ON issues(key_id);
    """)
    # частичные индексы по changelog
    pg_hook.run("""
        CREATE INDEX IF NOT EXISTS idx_changelog_sprint_to
          ON raw_jira.changelog(issue_key, change_date)
          WHERE field='Sprint' AND to_value_id IS NOT NULL;
    """)
    pg_hook.run("""
        CREATE INDEX IF NOT EXISTS idx_changelog_sprint_from
          ON raw_jira.changelog(issue_key, change_date)
          WHERE field='Sprint' AND from_value_id IS NOT NULL;
    """)
    pg_hook.run("""
        CREATE INDEX IF NOT EXISTS idx_changelog_fix_to
          ON raw_jira.changelog(issue_key, change_date)
          WHERE field IN ('Fix Version/s','Fix Version','fixVersions') AND to_value_id IS NOT NULL;
    """)
    pg_hook.run("""
        CREATE INDEX IF NOT EXISTS idx_changelog_fix_from
          ON raw_jira.changelog(issue_key, change_date)
          WHERE field IN ('Fix Version/s','Fix Version','fixVersions') AND from_value_id IS NOT NULL;
    """)

    # Финальное состояние (учитывает все перемещения и списки) + синхронизация (insert + delete)
    # Создаём временную таблицу с последним действием по каждой паре (issue, iteration)
    sql_build_latest = """
    CREATE TEMP TABLE tmp_issue_iteration_latest ON COMMIT DROP AS
    WITH raw_events AS (
      SELECT c.issue_key,
             trim(val)::text AS external_id,
             NULL::text AS iteration_name,
             c.change_date,
             'added'::text AS action
      FROM raw_jira.changelog c
      CROSS JOIN LATERAL regexp_split_to_table(c.to_value_id::text, '\\s*,\\s*') AS val
      WHERE (c.field = 'Sprint' OR c.field IN ('Fix Version/s','Fix Version','fixVersions'))
        AND c.to_value_id IS NOT NULL

      UNION ALL

      SELECT c.issue_key,
             trim(val)::text AS external_id,
             NULL::text AS iteration_name,
             c.change_date,
             'removed'::text AS action
      FROM raw_jira.changelog c
      CROSS JOIN LATERAL regexp_split_to_table(c.from_value_id::text, '\\s*,\\s*') AS val
      WHERE (c.field = 'Sprint' OR c.field IN ('Fix Version/s','Fix Version','fixVersions'))
        AND c.from_value_id IS NOT NULL

      UNION ALL

      SELECT c.issue_key,
             NULL::text AS external_id,
             trim(val)::text AS iteration_name,
             c.change_date,
             'added'::text AS action
      FROM raw_jira.changelog c
      CROSS JOIN LATERAL regexp_split_to_table(c.to_value::text, '\\s*,\\s*') AS val
      WHERE (c.field = 'Sprint' OR c.field IN ('Fix Version/s','Fix Version','fixVersions'))
        AND c.to_value IS NOT NULL

      UNION ALL

      SELECT c.issue_key,
             NULL::text AS external_id,
             trim(val)::text AS iteration_name,
             c.change_date,
             'removed'::text AS action
      FROM raw_jira.changelog c
      CROSS JOIN LATERAL regexp_split_to_table(c.from_value::text, '\\s*,\\s*') AS val
      WHERE (c.field = 'Sprint' OR c.field IN ('Fix Version/s','Fix Version','fixVersions'))
        AND c.from_value IS NOT NULL
    ),
    resolved AS (
      SELECT i.id AS issue_id,
             it.id AS iteration_id,
             e.action,
             e.change_date
      FROM raw_events e
      JOIN issues i ON i.key_id = e.issue_key
      JOIN iterations it ON it.project_id = i.project_id AND (
           (e.external_id IS NOT NULL AND it.external_id = e.external_id)
        OR (e.iteration_name IS NOT NULL AND it.name = e.iteration_name)
      )
    ),
    latest AS (
      SELECT issue_id, iteration_id, max(change_date) AS last_change
      FROM resolved
      GROUP BY issue_id, iteration_id
    )
    SELECT r.issue_id, r.iteration_id, r.action
    FROM latest l
    JOIN resolved r
      ON r.issue_id = l.issue_id AND r.iteration_id = l.iteration_id AND r.change_date = l.last_change;
    """

    # Выполним полную синхронизацию в ОДНОМ соединении, чтобы временные таблицы были доступны
    sql_sync = sql_build_latest + "\n" + """
      -- финальные пары из changelog
      CREATE TEMP TABLE tmp_final_issue_iteration_pairs ON COMMIT DROP AS
      SELECT issue_id, iteration_id
      FROM tmp_issue_iteration_latest
      WHERE action = 'added';

      -- текущие спринты из custom_field_values
      CREATE TEMP TABLE tmp_current_issue_iteration_pairs ON COMMIT DROP AS
      WITH sprint_cf AS (
        SELECT cf.id AS custom_field_id
        FROM custom_fields cf
        WHERE cf.name ILIKE 'Sprint'
           OR cf.external_key IN (SELECT id FROM raw_jira.fields WHERE name ILIKE 'Sprint')
      ), current_sprints AS (
        SELECT
          i.id AS issue_id,
          i.project_id,
          trim(elem->>'id') AS external_id
        FROM custom_field_values cfv
        JOIN sprint_cf sc ON sc.custom_field_id = cfv.custom_field_id
        JOIN issues i ON i.id = cfv.issue_id
        CROSS JOIN LATERAL (
          SELECT e FROM jsonb_array_elements(CASE WHEN jsonb_typeof(cfv.value)='array' THEN cfv.value ELSE '[]'::jsonb END) AS e
          UNION ALL
          SELECT cfv.value WHERE jsonb_typeof(cfv.value)='object'
        ) AS j(elem)
        WHERE (elem ? 'id')
      )
      SELECT c.issue_id, it.id AS iteration_id
      FROM current_sprints c
      JOIN iterations it ON it.project_id = c.project_id AND it.external_id = c.external_id;

      -- объединённое множество для сохранения
      -- ВАЖНО: если changelog явно показывает, что пара была REMOVED,
      -- то не сохраняем её даже если custom_field_values содержит текущий спринт.
      CREATE TEMP TABLE tmp_preserve_issue_iteration_pairs ON COMMIT DROP AS
      SELECT * FROM tmp_final_issue_iteration_pairs
      UNION
      SELECT c.issue_id, c.iteration_id
      FROM tmp_current_issue_iteration_pairs c
      LEFT JOIN tmp_issue_iteration_latest l
        ON l.issue_id = c.issue_id AND l.iteration_id = c.iteration_id
      WHERE l.issue_id IS NULL OR l.action <> 'removed';

      -- вставка недостающих и удаление устаревших с возвратом счётчиков
      WITH ins AS (
        INSERT INTO issue_iterations (id, issue_id, iteration_id)
        SELECT gen_random_uuid(), f.issue_id, f.iteration_id
        FROM tmp_preserve_issue_iteration_pairs f
        ON CONFLICT (issue_id, iteration_id) DO NOTHING
        RETURNING 1
      ), del AS (
        DELETE FROM issue_iterations ii
        WHERE NOT EXISTS (
          SELECT 1 FROM tmp_preserve_issue_iteration_pairs f
          WHERE f.issue_id = ii.issue_id AND f.iteration_id = ii.iteration_id
        )
        RETURNING 1
      )
      SELECT (SELECT COUNT(*) FROM ins) AS inserted, (SELECT COUNT(*) FROM del) AS deleted;
    """

    try:
        res = pg_hook.get_first(sql_sync)
        inserted = res[0] if res else 0
        deleted = res[1] if res and len(res) > 1 else 0
    except Exception as e:
        logging.exception("issue_iterations sync failed: %s", e)
        raise

    logging.info("Issue iterations sync: inserted=%s, deleted=%s", inserted, deleted)
    
    # Проверим количество созданных записей
    count_sql = "SELECT COUNT(*) FROM issue_iterations;"
    count = pg_hook.get_first(count_sql)[0]
    logging.info(f"Issue iterations loaded successfully: {count} records")

# @anchor:dag:load_issue_iteration_history
def load_issue_iteration_history(**kwargs):
    """Загружает историю изменений связей задач с итерациями из changelog"""
    pg_hook = PostgresHook(postgres_conn_id='postgres_default')
    
    # Skip gracefully if table doesn't exist in this schema variant
    if not _table_exists(pg_hook, 'public', 'issue_iteration_history'):
        logging.warning("Table issue_iteration_history does not exist, skipping task")
        return
    
    # Проверяем, существует ли таблица changelog
    check_sql = """
    SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'raw_jira' 
        AND table_name = 'changelog'
    );
    """
    
    changelog_exists = pg_hook.get_first(check_sql)[0]
    
    if not changelog_exists:
        logging.warning("Table raw_jira.changelog does not exist, skipping issue iteration history")
        return
    
    sql = """
    INSERT INTO issue_iteration_history (id, issue_id, iteration_id, action, changed_at)
    -- added
    SELECT gen_random_uuid(), i.id, it.id, 'added', c.change_date
    FROM raw_jira.changelog c
    JOIN issues i      ON i.key_id = c.issue_key
    CROSS JOIN LATERAL regexp_split_to_table(c.to_value_id::text, '\\s*,\\s*') AS val(ext_id)
    JOIN iterations it ON it.project_id = i.project_id AND it.external_id = trim(val.ext_id)
    WHERE (c.field = 'Sprint' OR c.field IN ('Fix Version/s','Fix Version','fixVersions'))
      AND c.to_value_id IS NOT NULL
      AND NOT EXISTS (
        SELECT 1 FROM issue_iteration_history h
        WHERE h.issue_id = i.id AND h.iteration_id = it.id AND h.action = 'added' AND h.changed_at = c.change_date
      )

    UNION ALL

    -- removed
    SELECT gen_random_uuid(), i.id, it.id, 'removed', c.change_date
    FROM raw_jira.changelog c
    JOIN issues i      ON i.key_id = c.issue_key
    CROSS JOIN LATERAL regexp_split_to_table(c.from_value_id::text, '\\s*,\\s*') AS val(ext_id)
    JOIN iterations it ON it.project_id = i.project_id AND it.external_id = trim(val.ext_id)
    WHERE (c.field = 'Sprint' OR c.field IN ('Fix Version/s','Fix Version','fixVersions'))
      AND c.from_value_id IS NOT NULL
      AND NOT EXISTS (
        SELECT 1 FROM issue_iteration_history h
        WHERE h.issue_id = i.id AND h.iteration_id = it.id AND h.action = 'removed' AND h.changed_at = c.change_date
      );
    """
    
    pg_hook.run(sql)
    logging.info("Issue iteration history loaded successfully")

# @anchor:dag:load_custom_field_values
def load_custom_field_values(**kwargs):
    """Загружает значения кастомных полей из raw_jira в таблицу custom_field_values"""
    pg_hook = PostgresHook(postgres_conn_id='postgres_default')

    # New: allow filters via conf/params
    conf = _get_conf(kwargs)
    filter_keys = conf.get('project_keys') if isinstance(conf, dict) else None
    user_id = conf.get('user_id') if isinstance(conf, dict) else None
    integration_uuid = conf.get('integration_uuid') if isinstance(conf, dict) else None
    
    # Получаем список всех таблиц issues__raw_data__fields__customfield_* для VALUES
    sql_get_tables = """
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'raw_jira' 
    AND table_name LIKE 'issues__raw_data__fields__customfield_%'
    AND table_name NOT LIKE '%content%'
    AND table_name NOT LIKE '%marks%'
    AND table_name NOT LIKE '%attrs%'
    """
    
    tables = pg_hook.get_records(sql_get_tables)
    logging.info(f"Found {len(tables)} custom field value tables: {[t[0] for t in tables]}")
    
    if len(tables) == 0:
        # Проверим, какие таблицы вообще есть в raw_jira
        all_tables_sql = """
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'raw_jira' 
        ORDER BY table_name
        """
        all_tables = pg_hook.get_records(all_tables_sql)
        logging.info(f"All tables in raw_jira: {[t[0] for t in all_tables]}")
        # even if no per-field tables exist, we may still have flat list table
        # fall through to try issues__custom_fields_list below
    # --- New: fallback - load from raw_jira.issues__custom_fields_list if present ---
    try:
        if _table_exists(pg_hook, 'raw_jira', 'issues__custom_fields_list'):
            cnt = pg_hook.get_first("SELECT COUNT(1) FROM raw_jira.issues__custom_fields_list;")[0]
            logging.info(f"raw_jira.issues__custom_fields_list exists, rows={cnt}")
            if cnt and cnt > 0:
                # ensure custom_fields entries per project
                ensure_sql = """
                INSERT INTO custom_fields (id, project_id, name, external_key, description)
                SELECT DISTINCT
                    gen_random_uuid() as id,
                    p.id as project_id,
                    t.field_id as name,
                    t.field_id as external_key,
                    'Custom field auto-created from issues__custom_fields_list' as description
                FROM raw_jira.issues__custom_fields_list t
                JOIN issues i ON i.key_id = t.issue_key
                JOIN projects p ON p.external_key = SPLIT_PART(t.issue_key, '-', 1)
                WHERE t.field_id LIKE 'customfield_%'
                ON CONFLICT (project_id, external_key) DO NOTHING;
                """
                pg_hook.run(ensure_sql)

                # upsert values from the flat list
                ins_sql = """
                WITH m AS (
                  SELECT i.id AS issue_id, i.project_id, t.field_id AS field_id, t.value as value
                  FROM raw_jira.issues__custom_fields_list t
                  JOIN issues i ON i.key_id = t.issue_key
                  WHERE t.field_id LIKE 'customfield_%' AND t.value IS NOT NULL
                ), cf AS (
                  SELECT id, project_id, external_key FROM custom_fields
                )
                INSERT INTO custom_field_values (id, issue_id, custom_field_id, value, updated_at)
                SELECT gen_random_uuid(), m.issue_id, cf.id, m.value::jsonb, NOW()
                FROM m
                JOIN cf ON cf.external_key = m.field_id AND cf.project_id = m.project_id
                ON CONFLICT (issue_id, custom_field_id) DO NOTHING;
                """
                pg_hook.run(ins_sql)
                logging.info("Loaded custom field values from issues__custom_fields_list fallback")
    except Exception as e:
        logging.warning(f"Fallback load from issues__custom_fields_list failed: {e}")

    # Initialize and compute once before loop: whether raw_jira.issues has raw_data
    has_raw_data_col = False
    try:
        has_raw_data_col = bool(
            pg_hook.get_first(
                """
                SELECT EXISTS (
                  SELECT 1 FROM information_schema.columns
                  WHERE table_schema = 'raw_jira' AND table_name = 'issues' AND column_name = 'raw_data'
                );
                """
            )[0]
        )
    except Exception:
        has_raw_data_col = False

    for table_record in tables:
        table_name = table_record[0]
        field_id = table_name.replace('issues__raw_data__fields__', '')
        
        # Проверяем структуру таблицы и количество записей
        check_count_sql = f"SELECT COUNT(*) FROM raw_jira.{table_name};"
        check_columns_sql = f"""
        SELECT array_agg(column_name) as columns
        FROM information_schema.columns c
        WHERE c.table_schema = 'raw_jira' 
          AND c.table_name = '{table_name}';
        """
        
        try:
            record_count = pg_hook.get_first(check_count_sql)[0]
            columns_result = pg_hook.get_first(check_columns_sql)
            columns = columns_result[0] if columns_result else []
            
            logging.info(f"Table {table_name}: {record_count} records, columns: {columns}")
            
            if record_count == 0:
                logging.warning(f"Table {table_name} is empty, skipping")
                continue
                
        except Exception as e:
            logging.error(f"Error checking table {table_name}: {e}")
            continue
        
        # Определим human-readable имя поля (fallback на ID)
        field_display_name = field_id
        try:
            nm = pg_hook.get_first(
                f"SELECT name FROM raw_jira.fields WHERE id = '{field_id}' LIMIT 1;"
            )
            if nm and nm[0]:
                field_display_name = nm[0]
        except Exception:
            pass

        # Перед загрузкой значений гарантируем наличие записи в custom_fields
        # для данного поля и каждого проекта, встретившегося в источнике
        try:
            sql_ensure_cf = f"""
            INSERT INTO custom_fields (id, project_id, name, external_key, description)
            SELECT DISTINCT
                gen_random_uuid() as id,
                i.project_id,
                '{field_display_name}' as name,
                '{field_id}' as external_key,
                'Custom field auto-created by load_custom_field_values' as description
            FROM raw_jira.{table_name} cfv
            JOIN raw_jira.issues ri ON ri._dlt_id = cfv._dlt_parent_id
            JOIN issues i ON i.key_id = ri.issue_key
            LEFT JOIN custom_fields cf
              ON cf.project_id = i.project_id AND cf.external_key = '{field_id}'
            WHERE cf.id IS NULL;
            """
            pg_hook.run(sql_ensure_cf)
        except Exception as e:
            logging.warning(f"Failed to ensure custom_fields for {field_id}: {e}")

        # Пытаемся два подхода: 1) из отдельных таблиц DLT, 2) из custom_fields JSON в issues (только если колонка raw_data существует)
        
        # Подход 1: Из отдельных таблиц DLT (старый способ)
        sql_dlt_tables = f"""
        WITH selected AS (
            SELECT DISTINCT ON (i.id, cf.id)
                i.id as issue_id,
                cf.id as custom_field_id,
                (to_jsonb(cfv) - '_dlt_id' - '_dlt_load_id' - '_dlt_parent_id' - '_dlt_list_idx') as value
            FROM raw_jira.{table_name} cfv
            JOIN raw_jira.issues ri ON ri._dlt_id = cfv._dlt_parent_id
            JOIN issues i ON i.key_id = ri.issue_key
            JOIN custom_fields cf ON cf.external_key = '{field_id}' AND cf.project_id = i.project_id
            WHERE (to_jsonb(cfv) - '_dlt_id' - '_dlt_load_id' - '_dlt_parent_id' - '_dlt_list_idx') != '{{}}'::jsonb
            ORDER BY i.id, cf.id, cfv._dlt_list_idx DESC
        )
        INSERT INTO custom_field_values (id, issue_id, custom_field_id, value, updated_at)
        SELECT
            gen_random_uuid() as id,
            s.issue_id,
            s.custom_field_id,
            s.value,
            NOW() as updated_at
        FROM selected s
        ON CONFLICT (issue_id, custom_field_id) DO UPDATE SET
            value = EXCLUDED.value,
            updated_at = NOW();
        """
        
        # Подход 2: Из raw_data->'fields' JSON в issues (новый способ) — только когда колонка raw_data есть
        has_raw_data_col = False
        try:
            has_raw_data_col = bool(
                pg_hook.get_first(
                    """
                    SELECT EXISTS (
                      SELECT 1 FROM information_schema.columns
                      WHERE table_schema = 'raw_jira' AND table_name = 'issues' AND column_name = 'raw_data'
                    );
                    """
                )[0]
            )
        except Exception:
            has_raw_data_col = False

        sql_json_fields = None
        if has_raw_data_col:
            sql_json_fields = f"""
            INSERT INTO custom_field_values (id, issue_id, custom_field_id, value, updated_at)
            SELECT DISTINCT 
                gen_random_uuid() as id,
                i.id as issue_id,
                cf.id as custom_field_id,
                (iss.raw_data->'fields'->>'{field_id}')::jsonb as value,
                NOW() as updated_at
            FROM raw_jira.issues iss
            JOIN issues i ON i.key_id = iss.issue_key
            JOIN custom_fields cf ON cf.external_key = '{field_id}' AND cf.project_id = i.project_id
            WHERE iss.raw_data->'fields' ? '{field_id}'
              AND iss.raw_data->'fields'->>'{field_id}' IS NOT NULL
              AND iss.raw_data->'fields'->>'{field_id}' != ''
            ON CONFLICT (issue_id, custom_field_id) DO UPDATE SET
                value = EXCLUDED.value,
                updated_at = NOW();
            """
        
        # Пробуем сначала подход 1 (DLT таблицы), потом подход 2 (JSON)
        sql = sql_dlt_tables
        
        try:
            result = pg_hook.run(sql)
            # Проверяем количество вставленных записей
            count_sql = f"""
            SELECT COUNT(*) FROM custom_field_values cfv
            JOIN custom_fields cf ON cf.id = cfv.custom_field_id
            WHERE cf.external_key = '{field_id}';
            """
            inserted_count = pg_hook.get_first(count_sql)[0]

            # Если DLT-таблицы не дали результатов, пробуем JSON-подход только при наличии raw_data
            if inserted_count == 0 and has_raw_data_col and sql_json_fields:
                logging.info(f"No data from DLT tables for {field_id}, trying JSON approach")
                try:
                    pg_hook.run(sql_json_fields)
                    inserted_count = pg_hook.get_first(count_sql)[0]
                    logging.info(f"JSON approach for {field_id}: inserted {inserted_count} records")
                except Exception as json_e:
                    logging.error(f"JSON approach also failed for {field_id}: {json_e}")

            logging.info(f"Loaded custom field values for: {field_id} from table {table_name}, total inserted: {inserted_count}")
        except Exception as e:
            logging.error(f"Error loading custom field values for {field_id} from {table_name}: {e}")
            # Пробуем JSON-подход только при наличии raw_data
            if has_raw_data_col and sql_json_fields:
                try:
                    logging.info(f"Trying JSON fallback for {field_id}")
                    pg_hook.run(sql_json_fields)
                    count_sql = f"""
                    SELECT COUNT(*) FROM custom_field_values cfv
                    JOIN custom_fields cf ON cf.id = cfv.custom_field_id
                    WHERE cf.external_key = '{field_id}';
                    """
                    inserted_count = pg_hook.get_first(count_sql)[0]
                    logging.info(f"JSON fallback for {field_id}: inserted {inserted_count} records")
                except Exception as json_e:
                    logging.error(f"JSON fallback also failed for {field_id}: {json_e}")
    
    # Дополнительно: загружаем все кастомные поля из JSON в raw_jira.issues
    # Это покрывает случаи, когда DLT не создал отдельные таблицы
    # Универсальная заливка из JSON (если колонка raw_data существует). Иначе — пропускаем.
    if has_raw_data_col:
        try:
            where_proj4 = ""
            params4 = []
            if filter_keys:
                placeholders = ','.join(['%s'] * len(filter_keys))
                if all(_looks_like_uuid(k) for k in filter_keys):
                    where_proj4 += f" AND p.id IN ({placeholders})"
                else:
                    where_proj4 += f" AND p.external_key IN ({placeholders})"
                params4.extend(filter_keys)
            if user_id and _looks_like_uuid(user_id):
                where_proj4 += " AND p.user_id = %s::uuid"
                params4.append(user_id)
            if integration_uuid and _looks_like_uuid(integration_uuid):
                where_proj4 += " AND p.tool_integration_id = %s::uuid"
                params4.append(integration_uuid)

            sql_all_json_fields = f"""
            INSERT INTO custom_field_values (id, issue_id, custom_field_id, value, updated_at)
            SELECT DISTINCT 
                gen_random_uuid() as id,
                i.id as issue_id,
                cf.id as custom_field_id,
                (iss.raw_data->'fields'->cf.external_key)::jsonb as value,
                NOW() as updated_at
            FROM raw_jira.issues iss
            JOIN issues i ON i.key_id = iss.issue_key
            JOIN custom_fields cf ON cf.project_id = i.project_id
            JOIN projects p ON p.id = i.project_id
            WHERE (iss.raw_data->'fields'->cf.external_key) IS NOT NULL
              AND cf.external_key LIKE 'customfield_%'
              {where_proj4}
            ON CONFLICT (issue_id, custom_field_id) DO UPDATE SET
                value = EXCLUDED.value,
                updated_at = NOW();
            """
            pg_hook.run(sql_all_json_fields, parameters=tuple(params4) if params4 else None)
            logging.info("All custom fields from JSON loaded")
        except Exception as e:
            logging.warning(f"All custom fields from JSON failed: {e}")

    # --- Additional fallback: always try loading from raw_jira.issues__custom_fields_list
    # This covers cases where some custom fields (e.g. Sprint) were not materialized as separate DLT tables
    try:
        if _table_exists(pg_hook, 'raw_jira', 'issues__custom_fields_list'):
            cnt = pg_hook.get_first("SELECT COUNT(1) FROM raw_jira.issues__custom_fields_list;")[0]
            logging.info(f"issues__custom_fields_list present, rows={cnt}")
            if cnt and cnt > 0:
                # ensure custom_fields entries per project/field
                ensure_sql = """
                INSERT INTO custom_fields (id, project_id, name, external_key, description)
                SELECT DISTINCT
                    gen_random_uuid() as id,
                    p.id as project_id,
                    t.field_id as name,
                    t.field_id as external_key,
                    'Custom field auto-created from issues__custom_fields_list (post)' as description
                FROM raw_jira.issues__custom_fields_list t
                JOIN issues i ON i.key_id = t.issue_key
                JOIN projects p ON p.external_key = SPLIT_PART(t.issue_key, '-', 1)
                WHERE t.field_id LIKE 'customfield_%'
                ON CONFLICT (project_id, external_key) DO NOTHING;
                """
                pg_hook.run(ensure_sql)

                # upsert values from the flat list for any fields
                ins_sql = """
                WITH m AS (
                  SELECT i.id AS issue_id, i.project_id, t.field_id AS field_id, t.value as value
                  FROM raw_jira.issues__custom_fields_list t
                  JOIN issues i ON i.key_id = t.issue_key
                  WHERE t.field_id LIKE 'customfield_%' AND t.value IS NOT NULL
                ), cf AS (
                  SELECT id, project_id, external_key FROM custom_fields
                )
                INSERT INTO custom_field_values (id, issue_id, custom_field_id, value, updated_at)
                SELECT gen_random_uuid(), m.issue_id, cf.id, m.value::jsonb, NOW()
                FROM m
                JOIN cf ON cf.external_key = m.field_id AND cf.project_id = m.project_id
                ON CONFLICT (issue_id, custom_field_id) DO NOTHING;
                """
                pg_hook.run(ins_sql)
                logging.info("Loaded custom field values from issues__custom_fields_list (post-processing)")
    except Exception as e:
        logging.warning(f"Post-processing load from issues__custom_fields_list failed: {e}")
    
    # Финальная проверка
    total_values_sql = "SELECT COUNT(*) FROM custom_field_values;"
    total_values = pg_hook.get_first(total_values_sql)[0]
    logging.info(f"Custom field values loading completed. Total values: {total_values}")

    
# @anchor:dag:backfill_issue_iterations_from_current
def backfill_issue_iterations_from_current(**kwargs):
    """Бэкфилл связей задач со спринтами/релизами и истории 'added' из текущих значений полей.
    Покрывает случай, когда задача создана уже внутри спринта/релиза и в changelog нет события добавления.
    """
    pg = PostgresHook(postgres_conn_id='postgres_default')

    conf = _get_conf(kwargs)
    filter_keys = conf.get('project_keys') if isinstance(conf, dict) else None
    user_id = conf.get('user_id') if isinstance(conf, dict) else None
    integration_uuid = conf.get('integration_uuid') if isinstance(conf, dict) else None
    if filter_keys and not isinstance(filter_keys, list):
        filter_keys = [filter_keys]

    # Build project filter CTE
    proj_filter_clause = "WHERE 1=1"
    params: list = []
    if filter_keys:
        placeholders = ','.join(['%s'] * len(filter_keys))
        if all(_looks_like_uuid(k) for k in filter_keys):
            proj_filter_clause += f" AND id IN ({placeholders})"
        else:
            proj_filter_clause += f" AND external_key IN ({placeholders})"
        params.extend(filter_keys)
    if user_id and _looks_like_uuid(user_id):
        proj_filter_clause += " AND user_id = %s::uuid"
        params.append(user_id)
    if integration_uuid and _looks_like_uuid(integration_uuid):
        proj_filter_clause += " AND tool_integration_id = %s::uuid"
        params.append(integration_uuid)

    logging.info(f"Backfill params: project_keys={filter_keys}, user_id={user_id}, integration_uuid={integration_uuid}")

    # 1) Sprint backfill: safe normalization of JSON (array/object/string)
    sql_sprint_precheck = f"""
    WITH pf AS (
      SELECT id FROM projects {proj_filter_clause}
    ), issues_with_sprint_events AS (
      SELECT DISTINCT i.id AS issue_id
      FROM raw_jira.changelog c
      JOIN issues i ON i.key_id = c.issue_key
      JOIN pf ON pf.id = i.project_id
      WHERE c.field = 'Sprint'
    ), sprint_cf AS (
      SELECT cf.id AS custom_field_id
      FROM custom_fields cf
      WHERE cf.name ILIKE 'Sprint'
         OR cf.external_key IN (SELECT id FROM raw_jira.fields WHERE name ILIKE 'Sprint')
    ), current_sprints AS (
      SELECT
        i.id AS issue_id,
        i.project_id,
        trim(elem->>'id') AS external_id,
        i.created
      FROM custom_field_values cfv
      JOIN sprint_cf sc ON sc.custom_field_id = cfv.custom_field_id
      JOIN issues i ON i.id = cfv.issue_id
      JOIN pf ON pf.id = i.project_id
      CROSS JOIN LATERAL (
        SELECT e FROM jsonb_array_elements(CASE WHEN jsonb_typeof(cfv.value)='array' THEN cfv.value ELSE '[]'::jsonb END) AS e
        UNION ALL
        SELECT cfv.value WHERE jsonb_typeof(cfv.value)='object'
      ) AS j(elem)
      WHERE (elem ? 'id')
    ), sprint_missing AS (
      SELECT cs.issue_id, it.id AS iteration_id, cs.created
      FROM current_sprints cs
      JOIN iterations it ON it.project_id = cs.project_id AND it.external_id = cs.external_id
      LEFT JOIN issue_iterations ii ON ii.issue_id = cs.issue_id AND ii.iteration_id = it.id
      LEFT JOIN issues_with_sprint_events se ON se.issue_id = cs.issue_id
      WHERE ii.issue_id IS NULL AND se.issue_id IS NULL
    )
    SELECT COUNT(*) AS candidates, (SELECT COUNT(*) FROM sprint_missing) AS missing_links
    FROM current_sprints;
    """

    sql_sprint_insert = f"""
    WITH pf AS (
      SELECT id FROM projects {proj_filter_clause}
    ), issues_with_sprint_events AS (
      SELECT DISTINCT i.id AS issue_id
      FROM raw_jira.changelog c
      JOIN issues i ON i.key_id = c.issue_key
      JOIN pf ON pf.id = i.project_id
      WHERE c.field = 'Sprint'
    ), sprint_cf AS (
      SELECT cf.id AS custom_field_id
      FROM custom_fields cf
      WHERE cf.name ILIKE 'Sprint'
         OR cf.external_key IN (SELECT id FROM raw_jira.fields WHERE name ILIKE 'Sprint')
    ), current_sprints AS (
      SELECT
        i.id AS issue_id,
        i.project_id,
        trim(elem->>'id') AS external_id,
        i.created
      FROM custom_field_values cfv
      JOIN sprint_cf sc ON sc.custom_field_id = cfv.custom_field_id
      JOIN issues i ON i.id = cfv.issue_id
      JOIN pf ON pf.id = i.project_id
      CROSS JOIN LATERAL (
        SELECT e FROM jsonb_array_elements(CASE WHEN jsonb_typeof(cfv.value)='array' THEN cfv.value ELSE '[]'::jsonb END) AS e
        UNION ALL
        SELECT cfv.value WHERE jsonb_typeof(cfv.value)='object'
      ) AS j(elem)
      WHERE (elem ? 'id')
    ), sprint_missing AS (
      SELECT DISTINCT cs.issue_id, it.id AS iteration_id, cs.created
      FROM current_sprints cs
      JOIN iterations it ON it.project_id = cs.project_id AND it.external_id = cs.external_id
      LEFT JOIN issue_iterations ii ON ii.issue_id = cs.issue_id AND ii.iteration_id = it.id
      LEFT JOIN issues_with_sprint_events se ON se.issue_id = cs.issue_id
      WHERE ii.issue_id IS NULL AND se.issue_id IS NULL
    ), ins AS (
      INSERT INTO issue_iterations (id, issue_id, iteration_id)
      SELECT gen_random_uuid(), issue_id, iteration_id FROM sprint_missing
      ON CONFLICT (issue_id, iteration_id) DO NOTHING
      RETURNING 1
    )
    SELECT (SELECT COUNT(*) FROM ins) AS inserted_links;
    """

    sql_sprint_hist_insert = f"""
    WITH pf AS (
      SELECT id FROM projects {proj_filter_clause}
    ), sprint_cf AS (
      SELECT cf.id AS custom_field_id
      FROM custom_fields cf
      WHERE cf.name ILIKE 'Sprint'
         OR cf.external_key IN (SELECT id FROM raw_jira.fields WHERE name ILIKE 'Sprint')
    ), candidates AS (
      SELECT DISTINCT cs.issue_id, it.id AS iteration_id, cs.created
      FROM (
        SELECT
          i.id AS issue_id,
          i.project_id,
          trim(elem->>'id') AS external_id,
          i.created
        FROM custom_field_values cfv
        JOIN sprint_cf sc ON sc.custom_field_id = cfv.custom_field_id
        JOIN issues i ON i.id = cfv.issue_id
        JOIN pf ON pf.id = i.project_id
        CROSS JOIN LATERAL (
          SELECT e FROM jsonb_array_elements(CASE WHEN jsonb_typeof(cfv.value)='array' THEN cfv.value ELSE '[]'::jsonb END) AS e
          UNION ALL
          SELECT cfv.value WHERE jsonb_typeof(cfv.value)='object'
        ) AS j(elem)
        WHERE (elem ? 'id')
      ) cs
      JOIN iterations it ON it.project_id = cs.project_id AND it.external_id = cs.external_id
      JOIN issues i ON i.id = cs.issue_id
    ), hist_missing AS (
      SELECT c.* FROM candidates c
      LEFT JOIN issue_iteration_history h
        ON h.issue_id = c.issue_id AND h.iteration_id = c.iteration_id AND h.action = 'added' AND h.changed_at = c.created
      WHERE h.id IS NULL
    ), ins AS (
      INSERT INTO issue_iteration_history (id, issue_id, iteration_id, action, changed_at)
      SELECT gen_random_uuid(), issue_id, iteration_id, 'added', created FROM hist_missing
      RETURNING 1
    )
    SELECT (SELECT COUNT(*) FROM ins) AS inserted_history;
    """

    # Execute sprint backfill and log counts
    try:
        pre = pg.get_first(sql_sprint_precheck, parameters=tuple(params) if params else None)
        if pre:
            logging.info(f"Sprint precheck: candidates={pre[0]}, missing_links={pre[1]}")
        inserted = pg.get_first(sql_sprint_insert, parameters=tuple(params) if params else None)
        logging.info(f"Sprint links inserted: {inserted[0] if inserted else 0}")
        hist_ins = pg.get_first(sql_sprint_hist_insert, parameters=tuple(params) if params else None)
        logging.info(f"Sprint history inserted: {hist_ins[0] if hist_ins else 0}")
    except Exception as e:
        logging.exception(f"Sprint backfill failed: {e}")

    # 2) (Optional) Release backfill - disabled by default to avoid schema mismatches
    logging.info("Release backfill is disabled in this run. Enable after review if needed.")

# @anchor:dag:load_custom_field_history
def load_custom_field_history(**kwargs):
    """Загружает историю изменений кастомных полей из changelog"""
    pg_hook = PostgresHook(postgres_conn_id='postgres_default')
    
    # Проверяем, существует ли таблица changelog
    check_sql = """
    SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'raw_jira' 
        AND table_name = 'changelog'
    );
    """
    
    changelog_exists = pg_hook.get_first(check_sql)[0]
    
    if not changelog_exists:
        logging.warning("Table raw_jira.changelog does not exist, skipping custom field history")
        return
    
    # Проверим количество записей в changelog с кастомными полями
    # Сначала посмотрим на структуру таблицы changelog
    structure_sql = """
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_schema = 'raw_jira' 
      AND table_name = 'changelog'
    ORDER BY ordinal_position;
    """
    
    columns_info = pg_hook.get_records(structure_sql)
    logging.info(f"Changelog table structure: {columns_info}")
    
    # Посмотрим на примеры данных с доступными колонками
    sample_sql = """
    SELECT field, field_id, COUNT(*) as cnt
    FROM raw_jira.changelog 
    WHERE field IS NOT NULL OR field_id IS NOT NULL
    GROUP BY field, field_id
    ORDER BY cnt DESC
    LIMIT 20;
    """
    
    sample_data = pg_hook.get_records(sample_sql)
    logging.info(f"Sample changelog fields: {sample_data}")
    
    # Теперь ищем кастомные поля только по field (так как field_id не существует)
    check_sql = """
    SELECT COUNT(*) as total_changelog,
           COUNT(CASE WHEN field LIKE 'customfield_%' OR field_id LIKE 'customfield_%' THEN 1 END) as custom_field_changes,
           array_agg(DISTINCT COALESCE(field_id, field)) FILTER (WHERE (field LIKE 'customfield_%' OR field_id LIKE 'customfield_%')) as custom_fields
    FROM raw_jira.changelog;
    """
    
    changelog_stats = pg_hook.get_first(check_sql)
    total_changelog = changelog_stats[0] if changelog_stats else 0
    custom_field_changes_field = changelog_stats[1] if changelog_stats else 0
    custom_fields_field = changelog_stats[2] if changelog_stats else []
    
    logging.info(f"Changelog stats: total={total_changelog}")
    logging.info(f"Custom field changes by 'field': {custom_field_changes_field}, fields: {custom_fields_field}")
    
    # Используем только поле 'field' для поиска кастомных полей
    if custom_field_changes_field > 0:
        field_column = "COALESCE(c.field_id, c.field)"
        custom_field_changes = custom_field_changes_field
        custom_fields_in_changelog = custom_fields_field
        logging.info("Using COALESCE(field_id, field) for custom fields lookup")
    else:
        logging.warning("No custom field changes found in changelog")
        return
    
    # Проверим, есть ли соответствующие custom_fields в нашей таблице
    existing_fields_sql = """
    SELECT COUNT(*), array_agg(external_key) 
    FROM custom_fields 
    WHERE external_key IN (
        SELECT DISTINCT COALESCE(field_id, field)
        FROM raw_jira.changelog 
        WHERE COALESCE(field_id, field) LIKE 'customfield_%'
    );
    """
    
    existing_stats = pg_hook.get_first(existing_fields_sql)
    existing_count = existing_stats[0] if existing_stats else 0
    existing_fields = existing_stats[1] if existing_stats else []
    
    logging.info(f"Existing custom fields in our table: {existing_count}, fields: {existing_fields}")
    
    # Сначала загружаем историю для существующих custom_fields
    sql = """
    INSERT INTO custom_field_history (
        id, issue_id, custom_field_id, old_value, new_value, changed_at
    )
    SELECT DISTINCT 
        gen_random_uuid() as id,
        i.id as issue_id,
        cf.id as custom_field_id,
        CASE 
            WHEN c.from_value IS NOT NULL AND c.from_value != '' 
            THEN to_jsonb(c.from_value)
            ELSE NULL 
        END as old_value,
        CASE 
            WHEN c.to_value IS NOT NULL AND c.to_value != '' 
            THEN to_jsonb(c.to_value)
            ELSE NULL 
        END as new_value,
        c.change_date as changed_at
    FROM raw_jira.changelog c
    JOIN issues i ON i.key_id = c.issue_key
    JOIN custom_fields cf ON cf.external_key = COALESCE(c.field_id, c.field) AND cf.project_id = i.project_id
    WHERE COALESCE(c.field_id, c.field) LIKE 'customfield_%'
    AND (c.from_value IS NOT NULL OR c.to_value IS NOT NULL)
    AND c.change_date IS NOT NULL;
    """
    
    try:
        pg_hook.run(sql)
    except Exception as e:
        err = str(e)
        if 'duplicate key value violates unique constraint' in err or 'idx_custom_field_history_unique' in err:
            logging.info('Duplicate entries found while inserting custom_field_history; skipping duplicates')
        else:
            logging.error(f'Failed to insert existing custom field history: {e}')
            raise
    
    # Дополнительно: создаем custom_fields для всех полей из changelog, которых нет в таблице
    try:
        sql_create_missing_fields = """
        INSERT INTO custom_fields (id, project_id, name, external_key, description)
        SELECT DISTINCT
            gen_random_uuid() as id,
            i.project_id as project_id,
            COALESCE(c.field_id, c.field) as name,
            COALESCE(c.field_id, c.field) as external_key,
            'Custom field from changelog' as description
        FROM raw_jira.changelog c
        JOIN issues i ON i.key_id = c.issue_key
        WHERE COALESCE(c.field_id, c.field) LIKE 'customfield_%'
        AND NOT EXISTS (
            SELECT 1 FROM custom_fields cf 
            WHERE cf.external_key = COALESCE(c.field_id, c.field) 
            AND cf.project_id = i.project_id
        )
        ON CONFLICT (project_id, external_key) DO NOTHING;
        """
        pg_hook.run(sql_create_missing_fields)
        logging.info("Created missing custom fields from changelog")
        
        # Теперь загружаем историю для всех полей
        sql_all_history = """
        INSERT INTO custom_field_history (
            id, issue_id, custom_field_id, old_value, new_value, changed_at
        )
        SELECT DISTINCT 
            gen_random_uuid() as id,
            i.id as issue_id,
            cf.id as custom_field_id,
            CASE 
                WHEN c.from_value IS NOT NULL AND c.from_value != '' 
                THEN to_jsonb(c.from_value)
                ELSE NULL 
            END as old_value,
            CASE 
                WHEN c.to_value IS NOT NULL AND c.to_value != '' 
                THEN to_jsonb(c.to_value)
                ELSE NULL 
            END as new_value,
            c.change_date as changed_at
        FROM raw_jira.changelog c
        JOIN issues i ON i.key_id = c.issue_key
        JOIN custom_fields cf ON cf.external_key = COALESCE(c.field_id, c.field) AND cf.project_id = i.project_id
        WHERE COALESCE(c.field_id, c.field) LIKE 'customfield_%'
        AND (c.from_value IS NOT NULL OR c.to_value IS NOT NULL)
        AND c.change_date IS NOT NULL
        ON CONFLICT (issue_id, custom_field_id, changed_at) DO NOTHING;
        """
        pg_hook.run(sql_all_history)
        logging.info("Loaded history for all custom fields")
    except Exception as e:
        logging.warning(f"Failed to create missing fields or load all history: {e}")
    
    # Проверяем количество вставленных записей
    count_sql = "SELECT COUNT(*) FROM custom_field_history;"
    inserted_count = pg_hook.get_first(count_sql)[0]
    logging.info(f"Custom field history loaded successfully: {inserted_count} records")

# @anchor:dag:load_issue_status_history
def load_issue_status_history(**kwargs):
    """Загружает историю изменений статусов задач из changelog"""
    pg_hook = PostgresHook(postgres_conn_id='postgres_default')
    
    # Проверяем, существует ли таблица changelog
    check_sql = """
    SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'raw_jira' 
        AND table_name = 'changelog'
    );
    """
    
    changelog_exists = pg_hook.get_first(check_sql)[0]
    
    if not changelog_exists:
        logging.warning("Table raw_jira.changelog does not exist, skipping issue status history")
        return
    
    sql = """
    INSERT INTO issue_status_history (
        id, issue_id, from_status_id, to_status_id, changed_at
    )
    SELECT DISTINCT 
        gen_random_uuid() as id,
        i.id as issue_id,
        old_s.id as from_status_id,
        new_s.id as to_status_id,
        c.change_date as changed_at
    FROM raw_jira.changelog c
    JOIN issues i ON i.key_id = c.issue_key
    LEFT JOIN statuses old_s ON old_s.project_id = i.project_id AND old_s.name = c.from_value
    LEFT JOIN statuses new_s ON new_s.project_id = i.project_id AND new_s.name = c.to_value
    WHERE c.field = 'status'
    AND c.from_value IS NOT NULL 
    AND c.to_value IS NOT NULL
    AND old_s.id IS NOT NULL 
    AND new_s.id IS NOT NULL
    AND old_s.id IS DISTINCT FROM new_s.id
    ON CONFLICT (issue_id, from_status_id, to_status_id, changed_at) DO NOTHING;
    """
    
    pg_hook.run(sql)
    logging.info("Issue status history loaded successfully")

# @anchor:dag:load_custom_field_10036
def load_custom_field_10036(**kwargs):
    pg = PostgresHook(postgres_conn_id='postgres_default')

    def _src_table():
        # 1) hard table
        if _table_exists(pg, 'raw_jira', 'issues__raw_data__fields__customfield_10036'):
            cnt = pg.get_first("SELECT COUNT(1) FROM raw_jira.issues__raw_data__fields__customfield_10036;")[0]
            if cnt and cnt > 0:
                return "hard"
        # 2) generic list
        if _table_exists(pg, 'raw_jira', 'issues__custom_fields_list'):
            cnt = pg.get_first(
                """
                SELECT COUNT(1)
                FROM raw_jira.issues__custom_fields_list
                WHERE field_id = 'customfield_10036' AND value IS NOT NULL;
                """
            )[0]
            if cnt and cnt > 0:
                return "list"
        # 3) issues.story_points
        if _has_columns(pg, 'raw_jira', 'issues', ['story_points']):
            cnt = pg.get_first(
                """
                SELECT COUNT(1) FROM raw_jira.issues WHERE story_points IS NOT NULL;
                """
            )[0]
            if cnt and cnt > 0:
                return "issues"
        return None

    src = _src_table()
    if not src:
        logging.info("No source for customfield_10036 found — nothing to load")
        return

    # ensure custom_fields rows exist per project
    ensure_sql = """
    INSERT INTO custom_fields (id, project_id, name, external_key, description)
    SELECT DISTINCT
        gen_random_uuid(), p.id, 'Story Points', 'customfield_10036', 'Jira Story Points'
    FROM projects p
    JOIN (
        SELECT DISTINCT split_part(issue_key, '-', 1) AS proj_key
        FROM {src_table}
    ) s ON s.proj_key = p.external_key
    ON CONFLICT (project_id, external_key) DO NOTHING;
    """.format(src_table=(
        'raw_jira.issues__raw_data__fields__customfield_10036' if src=='hard' else
        'raw_jira.issues__custom_fields_list' if src=='list' else
        'raw_jira.issues'
    ))
    pg.run(ensure_sql)

    # upsert values
    if src == 'hard':
        ins = """
        WITH m AS (
          SELECT i.id AS issue_id, i.project_id, t.value::text AS sp
          FROM raw_jira.issues__raw_data__fields__customfield_10036 t
          JOIN issues i ON i.key_id = t.issue_key
          WHERE t.value IS NOT NULL
        ), cf AS (
          SELECT id, project_id FROM custom_fields WHERE external_key = 'customfield_10036'
        )
        INSERT INTO custom_field_values (id, issue_id, custom_field_id, value, updated_at)
        SELECT gen_random_uuid(), m.issue_id, cf.id, to_jsonb(m.sp::numeric), now()
        FROM m JOIN cf ON cf.project_id = m.project_id
        ON CONFLICT (issue_id, custom_field_id)
        DO UPDATE SET value = EXCLUDED.value, updated_at = now();
        """
    elif src == 'list':
        ins = """
        WITH m AS (
          SELECT i.id AS issue_id, i.project_id, (t.value)::text AS sp
          FROM raw_jira.issues__custom_fields_list t
          JOIN issues i ON i.key_id = t.issue_key
          WHERE t.field_id = 'customfield_10036' AND t.value IS NOT NULL
        ), cf AS (
          SELECT id, project_id FROM custom_fields WHERE external_key = 'customfield_10036'
        )
        INSERT INTO custom_field_values (id, issue_id, custom_field_id, value, updated_at)
        SELECT gen_random_uuid(), m.issue_id, cf.id, to_jsonb(m.sp::numeric), now()
        FROM m JOIN cf ON cf.project_id = m.project_id
        ON CONFLICT (issue_id, custom_field_id)
        DO UPDATE SET value = EXCLUDED.value, updated_at = now();
        """
    else:
        ins = """
        WITH m AS (
          SELECT i.id AS issue_id, i.project_id, r.story_points::text AS sp
          FROM raw_jira.issues r
          JOIN issues i ON i.key_id = r.issue_key
          WHERE r.story_points IS NOT NULL
        ), cf AS (
          SELECT id, project_id FROM custom_fields WHERE external_key = 'customfield_10036'
        )
        INSERT INTO custom_field_values (id, issue_id, custom_field_id, value, updated_at)
        SELECT gen_random_uuid(), m.issue_id, cf.id, to_jsonb(m.sp::numeric), now()
        FROM m JOIN cf ON cf.project_id = m.project_id
        ON CONFLICT (issue_id, custom_field_id)
        DO UPDATE SET value = EXCLUDED.value, updated_at = now();
        """
    pg.run(ins)
    logging.info("customfield_10036 loaded via source: %s", src)

# @anchor:dag:jira_full_loader_manual_dag
with DAG(
    'jira_full_loader_manual',
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,  # Только ручной запуск
    catchup=False,
    tags=['jira', 'loader', 'manual'],
    default_args={
        'retries': 2,
        'retry_delay': timedelta(minutes=2),
    },
    default_view='graph',
    description='Полная загрузка данных из raw_jira в структурированные таблицы (ручной запуск)',
    params={
        # @anchor:dag:params
        'project_uuids': Param(default=[], type=['null', 'array', 'string'], description="Project UUIDs or external keys (string/array). Prefer UUIDs."),
        'user_id': Param(default=None, type=['null', 'string'], description="User UUID"),
        'integration_uuid': Param(default=None, type=['null', 'string'], description="Tool integration UUID"),
        'date_from': Param(default=None, type=['null', 'string'], description="YYYY-MM-DD"),
        'date_to': Param(default=None, type=['null', 'string'], description="YYYY-MM-DD"),
        'mode': Param(default=None, type=['null', 'string'], description="manual | auto_single | auto_multi"),
        'full_recompute': Param(default=False, type=['boolean', 'string'], description="If true, do full recompute for selected projects/window"),
        'apply_filters': Param(default=False, type=['boolean', 'string'], description="Apply user_id/integration_uuid/date filters explicitly"),
    }
) as dag:
    
    # @anchor:dag:manual_check_schema
    t0 = PythonOperator(task_id='check_schema', python_callable=check_schema_or_fail)
    # @anchor:dag:manual_tasks
    t1 = PythonOperator(task_id='load_statuses', python_callable=load_statuses)
    t2 = PythonOperator(task_id='load_issue_types', python_callable=load_issue_types)
    t3 = PythonOperator(task_id='load_iteration_types', python_callable=load_iteration_types)
    t4 = PythonOperator(task_id='load_iteration_statuses', python_callable=load_iteration_statuses)
    t5 = PythonOperator(task_id='load_custom_fields', python_callable=load_custom_fields)
    t6 = PythonOperator(task_id='load_iterations', python_callable=load_iterations)
    t7 = PythonOperator(task_id='load_issues', python_callable=load_issues)
    t7_sp = PythonOperator(task_id='load_custom_field_10036', python_callable=load_custom_field_10036)
    t8 = PythonOperator(task_id='load_issue_iterations', python_callable=load_issue_iterations)
    t9 = PythonOperator(task_id='load_issue_iteration_history', python_callable=load_issue_iteration_history)
    t11 = PythonOperator(task_id='load_custom_field_history', python_callable=load_custom_field_history)
    t10 = PythonOperator(task_id='load_custom_field_values', python_callable=load_custom_field_values)
    t10b = PythonOperator(task_id='backfill_issue_iterations_from_current', python_callable=backfill_issue_iterations_from_current)
    t12 = PythonOperator(task_id='load_issue_status_history', python_callable=load_issue_status_history)

    # @anchor:dag:validate_fks
    def validate_fks(**kwargs):
        pg = PostgresHook(postgres_conn_id='postgres_default')
        checks = [
            ("issues missing type_id", "SELECT COUNT(*) FROM issues i LEFT JOIN issue_types t ON t.id = i.type_id WHERE i.type_id IS NULL OR t.id IS NULL"),
            ("issues missing current_status_id", "SELECT COUNT(*) FROM issues i LEFT JOIN statuses s ON s.id = i.current_status_id WHERE i.current_status_id IS NULL OR s.id IS NULL"),
            ("issue_iterations invalid pairs", "SELECT COUNT(*) FROM issue_iterations ii LEFT JOIN issues i ON i.id = ii.issue_id LEFT JOIN iterations it ON it.id = ii.iteration_id WHERE i.id IS NULL OR it.id IS NULL"),
            ("custom_field_values invalid pairs", "SELECT COUNT(*) FROM custom_field_values v LEFT JOIN issues i ON i.id = v.issue_id LEFT JOIN custom_fields cf ON cf.id = v.custom_field_id WHERE i.id IS NULL OR cf.id IS NULL"),
        ]
        for name, sql in checks:
            val = pg.get_first(sql)[0]
            if val and val > 0:
                raise Exception(f"FK validation failed: {name} = {val}")
        logging.info("FK validation passed")

    t_validate_fks = PythonOperator(task_id='validate_fks', python_callable=validate_fks)
    # Board-related loaders
    t_load_boards = PythonOperator(task_id='load_boards', python_callable=load_boards)
    t_load_board_columns = PythonOperator(task_id='load_board_columns', python_callable=load_board_columns)
    t_load_board_column_statuses = PythonOperator(task_id='load_board_column_statuses', python_callable=load_board_column_statuses)

    # @anchor:dag:manual_dependencies
    # Полная цепочка загрузки данных (чистые таблицы)
    t0 >> t1 >> t2 >> t3 >> t4 >> t5 >> t6 >> t7 >> t7_sp >> t8 >> t9 >> t11 >> t10 >> t10b >> t12 >> t_validate_fks >> t_load_boards >> t_load_board_columns >> t_load_board_column_statuses