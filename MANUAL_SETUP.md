# Manual SQL Setup Guide (Резервный вариант)

Если автоматизированные пайплайны не работают, вы можете вручную создать необходимые данные через SQL.

## Подключение к БД

```bash
# Подключитесь к PostgreSQL контейнеру
docker-compose exec db psql -U postgres -d metrics
```

## 1. Создание системного пользователя

```sql
-- Создайте системного пользователя для автоматизации
INSERT INTO platform.users (id, email, name, role, created_at, updated_at)
VALUES (
    '00000000-0000-0000-0000-000000000000'::uuid,
    'system@metrics.local',
    'System User',
    'admin',
    NOW(),
    NOW()
)
ON CONFLICT (email) DO NOTHING;
```

## 2. Регистрация Jira интеграции

```sql
-- Убедитесь, что тип интеграции Jira существует
INSERT INTO platform.integration_types (id, name, description)
VALUES (
    '10000000-0000-0000-0000-000000000001'::uuid,
    'jira_cloud',
    'Jira Cloud integration'
)
ON CONFLICT (name) DO NOTHING;

-- Создайте инстанс интеграции
INSERT INTO platform.tool_integrations (
    id,
    user_id,
    integration_type_id,
    name,
    config,
    is_active,
    created_at,
    updated_at
) VALUES (
    '20000000-0000-0000-0000-000000000001'::uuid,
    '00000000-0000-0000-0000-000000000000'::uuid,
    '10000000-0000-0000-0000-000000000001'::uuid,
    'Default Jira Integration',
    '{"base_url": "https://your-domain.atlassian.net", "email": "your-email@company.com"}'::jsonb,
    true,
    NOW(),
    NOW()
)
ON CONFLICT (id) DO NOTHING;
```

## 3. Создание платформенного проекта

```sql
-- Получите ID системной интеграции Jira
SELECT id FROM platform.tool_integrations ti
JOIN platform.users u ON ti.user_id = u.id
WHERE u.email = 'system@metrics.local'
  AND ti.integration_type_id = (
      SELECT id FROM platform.integration_types WHERE name = 'jira_cloud'
  );

-- Создайте платформенный проект (логический контейнер для всех Jira проектов)
INSERT INTO platform.projects (
    id,
    owner_user_id,
    tool_integration_id,
    external_key,
    external_id,
    name,
    is_active
) VALUES (
    '00000000-0000-0000-0000-000000000001'::uuid,
    (SELECT id FROM platform.users WHERE email = 'system@metrics.local'),
    (SELECT ti.id FROM platform.tool_integrations ti
     JOIN platform.users u ON ti.user_id = u.id
     WHERE u.email = 'system@metrics.local'
       AND ti.integration_type_id = (SELECT id FROM platform.integration_types WHERE name = 'jira_cloud')
     LIMIT 1),
    'JIRA',
    'jira-aggregated',
    'Jira - Aggregated Projects',
    true
)
ON CONFLICT (id) DO NOTHING;
```

## 4. Создание чистых слоёв схем (если они не существуют)

### Clean Jira Schema

```sql
-- Создайте чистую схему для Jira, если её нет
CREATE SCHEMA IF NOT EXISTS clean_jira;

-- Таблица проектов
CREATE TABLE IF NOT EXISTS clean_jira.projects (
    id BIGSERIAL PRIMARY KEY,
    platform_project_id UUID NOT NULL,
    external_id TEXT NOT NULL,
    external_key TEXT,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(platform_project_id, external_id)
);

-- Типы проблем
CREATE TYPE clean_jira.issue_hierarchy_level AS ENUM ('epic', 'story', 'task', 'subtask');

CREATE TABLE IF NOT EXISTS clean_jira.issue_types (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES clean_jira.projects(id),
    external_id TEXT NOT NULL,
    name TEXT NOT NULL,
    hierarchy_level clean_jira.issue_hierarchy_level,
    UNIQUE(project_id, external_id)
);

-- Статусы проблем
CREATE TYPE clean_jira.issue_status_category AS ENUM ('to_do', 'in_progress', 'done');

CREATE TABLE IF NOT EXISTS clean_jira.issue_statuses (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES clean_jira.projects(id),
    external_id TEXT NOT NULL,
    name TEXT NOT NULL,
    category clean_jira.issue_status_category,
    UNIQUE(project_id, external_id)
);

-- Пользователи Jira
CREATE TABLE IF NOT EXISTS clean_jira.jira_users (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES clean_jira.projects(id),
    external_id TEXT NOT NULL,
    display_name TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(project_id, external_id)
);

-- Проблемы
CREATE TABLE IF NOT EXISTS clean_jira.issues (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES clean_jira.projects(id),
    external_id TEXT NOT NULL,
    external_key TEXT,
    summary TEXT,
    description TEXT,
    type_id BIGINT REFERENCES clean_jira.issue_types(id),
    status_id BIGINT REFERENCES clean_jira.issue_statuses(id),
    jira_created_at TIMESTAMPTZ,
    jira_updated_at TIMESTAMPTZ,
    jira_resolved_at TIMESTAMPTZ,
    db_created_at TIMESTAMPTZ DEFAULT NOW(),
    db_updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(project_id, external_id)
);

-- Спринты
CREATE TYPE clean_jira.sprint_status AS ENUM ('future', 'active', 'closed');

CREATE TABLE IF NOT EXISTS clean_jira.sprints (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES clean_jira.projects(id),
    external_id TEXT NOT NULL,
    name TEXT,
    goal TEXT,
    status clean_jira.sprint_status,
    start_date TIMESTAMPTZ,
    end_date TIMESTAMPTZ,
    complete_date TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(project_id, external_id)
);
```

## 5. Создание статистических представлений (вручную)

```sql
-- Создайте метрики схему
CREATE SCHEMA IF NOT EXISTS metrics;

-- Представление Lead Time (пример)
CREATE OR REPLACE VIEW metrics.mv_lead_time AS
SELECT
    p.external_key as project_key,
    COUNT(DISTINCT i.id) as issues_count,
    AVG(EXTRACT(EPOCH FROM (i.jira_resolved_at - i.jira_created_at))) as avg_lead_time_seconds
FROM clean_jira.issues i
JOIN clean_jira.projects p ON i.project_id = p.id
WHERE i.jira_resolved_at IS NOT NULL
GROUP BY p.external_key;

-- Представление Velocity (пример)
CREATE OR REPLACE VIEW metrics.mv_velocity AS
SELECT
    s.name as sprint_name,
    p.external_key as project_key,
    COUNT(DISTINCT i.id) as completed_issues
FROM clean_jira.issues i
JOIN clean_jira.sprints s ON i.project_id = s.project_id
JOIN clean_jira.projects p ON i.project_id = p.id
WHERE i.jira_resolved_at IS NOT NULL
    AND s.status = 'closed'::clean_jira.sprint_status
GROUP BY s.name, p.external_key;
```

## 6. Загрузка сырых данных вручную (если нужно)

```sql
-- Если у вас уже есть сырые данные в raw_jira схеме
-- можно вручную синхронизировать их в чистый слой

-- Сначала создайте проекты в чистом слое
INSERT INTO clean_jira.projects (
    platform_project_id,
    external_id,
    external_key,
    name,
    created_at,
    updated_at
)
SELECT
    '00000000-0000-0000-0000-000000000001'::uuid,
    r.id::text,
    r.key,
    r.name,
    NOW(),
    NOW()
FROM raw_jira.projects r
ON CONFLICT (platform_project_id, external_id) DO NOTHING;

-- Затем синхронизируйте типы проблем
INSERT INTO clean_jira.issue_types (
    project_id,
    external_id,
    name,
    hierarchy_level
)
SELECT DISTINCT
    p.id,
    r.fields__issuetype__id,
    r.fields__issuetype__name,
    CASE
        WHEN r.fields__issuetype__name ILIKE '%epic%' THEN 'epic'::clean_jira.issue_hierarchy_level
        WHEN r.fields__issuetype__name ILIKE '%subtask%' THEN 'subtask'::clean_jira.issue_hierarchy_level
        WHEN r.fields__issuetype__name ILIKE '%story%' THEN 'story'::clean_jira.issue_hierarchy_level
        ELSE 'task'::clean_jira.issue_hierarchy_level
    END
FROM raw_jira.issues r
JOIN clean_jira.projects p ON r.fields__project__id::text = p.external_id
WHERE r.fields__issuetype__id IS NOT NULL
ON CONFLICT (project_id, external_id) DO NOTHING;
```

## 7. Проверка данных

```sql
-- Проверьте, что системный пользователь создан
SELECT * FROM platform.users WHERE email = 'system@metrics.local';

-- Проверьте интеграции
SELECT * FROM platform.tool_integrations;

-- Проверьте проекты
SELECT * FROM platform.projects;

-- Проверьте чистые данные
SELECT COUNT(*) as project_count FROM clean_jira.projects;
SELECT COUNT(*) as issue_count FROM clean_jira.issues;
SELECT COUNT(*) as sprint_count FROM clean_jira.sprints;
```

## 8. Запуск Dagster вручную (если данные готовы)

```bash
# Если вы вручную создали raw слой, можно запустить clean трансформацию
docker-compose exec app dagster job execute -j clean_jira_job

# Или запустить все Jira ассеты
docker-compose exec app dagster asset materialize --select "jira*"
```

## Troubleshooting

### Ошибка: "System Jira integration not found"

Если вы видите эту ошибку, убедитесь что запустили шаги 1-2 этого руководства:

```sql
-- Проверьте, существует ли системный пользователь
SELECT * FROM platform.users WHERE email = 'system@metrics.local';

-- Проверьте, существует ли интеграция
SELECT * FROM platform.tool_integrations ti
JOIN platform.users u ON ti.user_id = u.id
WHERE u.email = 'system@metrics.local';
```

### Ошибка: Foreign Key constraint failed

Убедитесь, что создали все таблицы в правильном порядке (проекты → типы → статусы → проблемы).

### Метрики не обновляются

После загрузки данных вручную обновите представления:

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY metrics.mv_lead_time;
REFRESH MATERIALIZED VIEW CONCURRENTLY metrics.mv_velocity;
```

## Использование в CI/CD

Если вы хотите автоматизировать эту настройку в CI/CD, создайте SQL миграцию:

```bash
# Создайте новую миграцию
docker-compose exec app alembic revision --message "manual_setup"

# Скопируйте SQL команды из этого файла в новую миграцию
# файл будет: db/migrations/versions/xxx_manual_setup.py
```

Пример миграции:

```python
def upgrade():
    op.execute("""
        -- Вставьте SQL команды отсюда
    """)

def downgrade():
    op.execute("""
        -- Откатите если нужно
    """)
```
