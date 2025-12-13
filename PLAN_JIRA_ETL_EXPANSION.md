# 📋 ПЛАН: Расширение Jira ETL для MVP (v2 - с insights из Airflow loader)

**Дата:** 2025-12-13
**Статус:** In Progress
**Основано на:** Old Airflow jira_full_loader_manual.py + Текущая Dagster реализация

---

## 🎯 Цель

Расширить текущий ETL (raw → clean) для заполнения всех таблиц `clean_jira` кроме исключенных.

**Исключены:**
- `jira_user_issue_roles`
- `relation_issue_types`, `relation_issue_issues`
- `issue_comment_blockings`, `comments`, `comment_issues`

**Включены (все остальные):**
- projects, issue_types, issue_statuses, jira_users
- issues
- sprints, sprint_issues, sprint_changelog, sprint_issues_changelog
- releases, release_issues
- field_keys, field_values, field_value_changelog
- boards, board_columns, board_column_statuses

---

## 📊 ЧАСТЬ 1: Порядок заполнения таблиц (по FK-PK зависимостям)

```
УРОВЕНЬ 0 - Независимые таблицы (base справочники)
├─ projects              ← raw_jira.projects
├─ issue_types           ← raw_jira.issues (fields__issuetype)
├─ issue_statuses        ← raw_jira.issues (fields__status)
└─ jira_users            ← raw_jira.users + issues (assignee, reporter, creator из fields)

УРОВЕНЬ 1 - Основные сущности
├─ issues                ← raw_jira.issues + FK на (projects, issue_types, issue_statuses)
├─ sprints               ← raw_jira.sprints + FK на projects
└─ releases              ← raw_jira.versions + FK на projects

УРОВЕНЬ 2 - Связи основных сущностей
├─ sprint_issues         ← raw_jira.issues.changelog (field='Sprint') → extract sprint_id + issue_id
│                         + raw_jira.sprint_issues (если загружена из API)
│                         + ФИНАЛЬНОЕ СОСТОЯНИЕ (added, not removed)
├─ release_issues        ← raw_jira.issues.changelog (field='Fix Version/s','fixVersions') → extract version_id + issue_id
│                         + ФИНАЛЬНОЕ СОСТОЯНИЕ (added, not removed)
└─ field_keys            ← raw_jira.issues (все ключи fields__*)

УРОВЕНЬ 3 - История и детали
├─ sprint_changelog      ← raw_jira.sprints (pre-load sprint properties from issues.changelog?)
│                         + raw_jira.issues.changelog (sprint field changes, если это есть)
├─ sprint_issues_changelog ← raw_jira.issues.changelog[field='Sprint'] (действия: added/removed)
│                            + FK на (sprints, issues, jira_users)
├─ field_values          ← raw_jira.issues (current field values) + FK на (issues, field_keys)
└─ field_value_changelog ← raw_jira.issues.changelog[field='customfield_*'] (все changes)
                           + FK на (issues, field_keys, jira_users)

УРОВЕНЬ 4 - Доски (опционально, но в MVP)
├─ boards                ← raw_jira.boards + FK на projects
├─ board_columns         ← raw_jira.board_configuration + FK на boards
└─ board_column_statuses ← raw_jira.board_configuration + FK на (board_columns, issue_statuses)
```

---

## 🔌 ЧАСТЬ 2: Структура raw_jira (что загружается в raw слой)

### Существующие таблицы (уже работают):

```sql
raw_jira.issues
  ├─ fields__issuetype__id, fields__issuetype__name
  ├─ fields__status__id, fields__status__name
  ├─ fields__project__id, fields__project__key
  ├─ fields__assignee__accountId, fields__assignee__displayName
  ├─ fields__reporter__accountId, fields__reporter__displayName
  ├─ fields__created, fields__updated
  ├─ rendered_fields__description
  ├─ changelog JSONB  ⭐ КЛЮЧЕВОЙ! Вся история здесь!
  └─ ... (все поля fields_*)

raw_jira.projects
  ├─ id (Jira project ID)
  ├─ key (PROJ)
  ├─ name
  └─ description

raw_jira.sprints
  ├─ id (sprint ID)
  ├─ name
  ├─ goal
  ├─ state (future, active, closed)
  ├─ start_date
  ├─ end_date
  ├─ complete_date
  └─ board_id

raw_jira.users
  ├─ account_id (Jira accountId)
  └─ display_name
```

### Новые таблицы (нужно добавить):

```sql
-- 1. raw_jira.sprint_issues
-- Связи спринтов и задач из GET /rest/agile/1.0/board/{id}/sprint/{sprintId}/issue
CREATE TABLE raw_jira.sprint_issues (
    sprint_id TEXT,
    issue_id TEXT,
    issue_key TEXT,
    board_id INT,
    PRIMARY KEY (sprint_id, issue_id)
);
-- Заполняется из API, но ТАКЖЕ вычисляется из changelog!

-- 2. raw_jira.versions
-- Релизы/версии проекта из GET /rest/api/3/project/{key}/versions
CREATE TABLE raw_jira.versions (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    name TEXT,
    description TEXT,
    status TEXT,
    start_date DATE,
    release_date DATE,
    released BOOLEAN,
    archived BOOLEAN
);

-- 3. raw_jira.board_configurations
-- Конфиги досок из GET /rest/agile/1.0/board/{id}/configuration
CREATE TABLE raw_jira.board_configurations (
    board_id INT PRIMARY KEY,
    columns_config JSONB  -- полный JSON конфига досок
);
```

### ⭐ КЛЮЧЕВАЯ ИНФОРМАЦИЯ В CHANGELOG

**Структура в raw_jira.issues.changelog (JSONB):**

```json
{
  "histories": [
    {
      "id": "456",
      "author": { "accountId": "..." },
      "created": "2024-01-15T10:30:00Z",
      "items": [
        {
          "field": "Sprint",
          "fieldId": "customfield_10001",
          "from": "1",                  // sprint ID (старый)
          "fromString": "Sprint 1",     // sprint name (старый)
          "to": "2",                    // sprint ID (новый)
          "toString": "Sprint 2"        // sprint name (новый)
        },
        {
          "field": "Fix Version/s",     // ИЛИ "fixVersions", "Fix Version"
          "from": "1,2",                // version IDs (старые, comma-separated!)
          "to": "2,3",                  // version IDs (новые)
          "fromString": "1.0,1.1",
          "toString": "1.1,2.0"
        },
        {
          "field": "customfield_10002",
          "from": "old_value",
          "to": "new_value"
        },
        {
          "field": "Status",
          "from": "10000",
          "to": "10001",
          "fromString": "To Do",
          "toString": "In Progress"
        }
      ]
    }
  ]
}
```

**Парсинг changelog:**
- `field == 'Sprint'` → **sprint_issues_changelog** + **sprint_issues** (final state)
- `field IN ('Fix Version/s', 'fixVersions', 'Fix Version')` → **release_issues_changelog** + **release_issues** (final state)
- `field LIKE 'customfield_%'` → **field_value_changelog** + **field_values** (current state)

**ВАЖНО:** Значения в `to` / `from` могут быть **comma-separated**! Нужно парсить через `regexp_split_to_table(val, '\s*,\s*')`

---

## 🔧 ЧАСТЬ 3: Требуемые Jira API эндпойнты (для raw.py)

### ✅ Уже реализовано:

| Эндпойнт | Таблица | Где |
|----------|---------|-----|
| `GET /rest/api/3/project/search` | raw_jira.projects | raw.py:78-105 |
| `GET /rest/api/3/search?expand=changelog,renderedFields&fields=*all` | raw_jira.issues | raw.py:34-76 |
| `GET /rest/api/3/user/assignable/search` | raw_jira.users | raw.py:151-178 |
| `GET /rest/agile/1.0/board` | (boards list) | raw.py:107-150 |
| `GET /rest/agile/1.0/board/{id}/sprint` | raw_jira.sprints | raw.py:107-150 |

### ❌ НУЖНО ДОБАВИТЬ:

| # | Эндпойнт | raw_jira таблица | Описание |
|---|----------|------------------|---------|
| 1 | `GET /rest/agile/1.0/board/{boardId}/sprint/{sprintId}/issue` | sprint_issues | **Задачи в конкретном спринте** (дополнить/валидировать changelog данные) |
| 2 | `GET /rest/api/3/project/{projectKey}/versions` | versions | **Релизы/версии** проекта |
| 3 | `GET /rest/agile/1.0/board/{boardId}/configuration` | board_configurations | **Конфигурация досок** (колонки и их статусы) |

**Параметры запросов:**
- pagination: `maxResults`, `startAt`
- expand: если нужны доп. поля
- filter by project: у проектов есть ключ (PROJ), используется в path или query

---

## 🔄 ЧАСТЬ 4: dlt ресурсы в raw.py (что добавить)

### Текущая структура jira_source():

```python
@dlt.source(name="jira")
def jira_source(base_url, email, api_token, projects=None):

    @dlt.resource(name="issues", write_disposition="merge", primary_key="id")
    def get_issues() → Iterator[dict]:
        # GET /rest/api/3/search с expand=changelog
        # ✅ УЖЕ ЕСТЬ

    @dlt.resource(name="projects", write_disposition="merge", primary_key="id")
    def get_projects() → Iterator[dict]:
        # ✅ УЖЕ ЕСТЬ

    @dlt.resource(name="sprints", write_disposition="merge", primary_key="id")
    def get_sprints() → Iterator[dict]:
        # ✅ УЖЕ ЕСТЬ

    @dlt.resource(name="users", write_disposition="merge", primary_key="accountId")
    def get_users() → Iterator[dict]:
        # ✅ УЖЕ ЕСТЬ

    # ❌ НУЖНЫ НОВЫЕ:

    @dlt.resource(name="sprint_issues", write_disposition="merge", primary_key=["sprint_id", "issue_id"])
    def get_sprint_issues() → Iterator[dict]:
        """Для каждого спринта: GET /rest/agile/1.0/board/{boardId}/sprint/{sprintId}/issue"""
        # 1. Получить все спринты из get_sprints()
        # 2. Для каждого спринта: GET /rest/agile/1.0/board/{board_id}/sprint/{sprint_id}/issue
        # 3. Yield (sprint_id, issue_id, issue_key, board_id)

    @dlt.resource(name="versions", write_disposition="merge", primary_key="id")
    def get_versions() → Iterator[dict]:
        """Для каждого проекта: GET /rest/api/3/project/{projectKey}/versions"""
        # 1. Получить все проекты из get_projects()
        # 2. Для каждого проекта: GET /rest/api/3/project/{project_key}/versions
        # 3. Yield (id, name, status, released, archived, start_date, release_date, description)

    @dlt.resource(name="board_configurations", write_disposition="merge", primary_key="board_id")
    def get_board_configurations() → Iterator[dict]:
        """Для каждой доски: GET /rest/agile/1.0/board/{boardId}/configuration"""
        # 1. Получить все доски (уже есть из sprints → board_id)
        # 2. Для каждой доски: GET /rest/agile/1.0/board/{board_id}/configuration
        # 3. Yield (board_id, columns_config_json)
```

---

## 🏗️ ЧАСТЬ 5: Трансформация в clean.py

### Существующие assets (развить):

#### `clean_jira_issues()` (раскрыть)

```python
@asset(deps=["raw_jira_data"])
def clean_jira_issues(...):
    # ✅ Projects
    # ✅ Issue types
    # ✅ Issue statuses
    # ✅ Jira users (из raw_jira.users + fields assignee/reporter/creator)
    # ✅ Issues
    # ➕ НОВОЕ: Extract field_keys из всех fields__* в issues

    # Логика:
    # 1. Из raw_jira.issues.fields__* извлечь все уникальные ключи
    # 2. Скомпилировать словарь: {field_key: field_name}
    # 3. INSERT INTO clean_jira.field_keys с этими данными
```

#### `clean_jira_sprints()` (развить)

```python
@asset(deps=["raw_jira_data"])
def clean_jira_sprints(...):
    # ✅ Существующее: INSERT INTO clean_jira.sprints из raw_jira.sprints
    # ➕ НОВОЕ: Заполнить sprint_issues из raw_jira.sprint_issues (если есть)
    # ➕ НОВОЕ: Заполнить sprint_issues из changelog (парсить field='Sprint')
    # ➕ НОВОЕ: Заполнить sprint_changelog из changelog (если sprint имеет history)

    # Логика для sprint_issues из changelog (CRITICAL для velocity!):
    # 1. SELECT * FROM raw_jira.issues WHERE changelog IS NOT NULL
    # 2. Для каждой history item с field='Sprint':
    #    a. from -> 'removed' action
    #    b. to -> 'added' action
    # 3. regexp_split_to_table() для распарсивания comma-separated sprint IDs
    # 4. Найти спринт по external_id из to/from
    # 5. Найти issue по external_id
    # 6. INSERT INTO clean_jira.sprint_issues (IF action='added' AND latest change)
    # 7. INSERT INTO clean_jira.sprint_issues_changelog с действиями (added/removed) + timestamp
```

### Новые assets:

#### `clean_jira_field_keys_and_values()` (CRITICAL!)

```python
@asset(deps=["clean_jira_issues"])
def clean_jira_field_keys_and_values(...):
    # Из clean_jira_issues мы уже извлекли field_keys
    # Теперь:
    # 1. INSERT INTO clean_jira.field_values (current state из raw_jira.issues.fields__)
    # 2. INSERT INTO clean_jira.field_value_changelog (из raw_jira.issues.changelog)

    # Для field_values:
    # - Скан raw_jira.issues по всем fields__*
    # - Для каждого issue + field: INSERT INTO field_values (issue_id, field_key_id, value)

    # Для field_value_changelog (ОЧЕНЬ CRITICAL!!!):
    # - Парсить changelog с field LIKE 'customfield_%'
    # - Для каждого change: INSERT INTO field_value_changelog
    #   (issue_id, field_key_id, old_value, new_value, changed_by_id, changed_at)
```

#### `clean_jira_releases()`, `clean_jira_release_issues()`

```python
@asset(deps=["clean_jira_issues"])
def clean_jira_releases(...):
    # INSERT INTO clean_jira.releases из raw_jira.versions

@asset(deps=["clean_jira_issues", "clean_jira_releases"])
def clean_jira_release_issues(...):
    # Из changelog: field IN ('Fix Version/s', 'fixVersions', 'Fix Version')
    # Логика аналогична sprint_issues:
    # 1. Парсить changelog
    # 2. regexp_split_to_table() для version IDs
    # 3. INSERT INTO clean_jira.release_issues (final state: added, not removed)
    # 4. INSERT INTO clean_jira.release_issues_changelog
```

#### `clean_jira_boards()`

```python
@asset(deps=["clean_jira_issues"])
def clean_jira_boards(...):
    # INSERT INTO clean_jira.boards из raw_jira.board_configurations
    # + INSERT INTO clean_jira.board_columns из конфига
    # + INSERT INTO clean_jira.board_column_statuses связывая статусы
```

---

## 📝 ЧАСТЬ 6: Парсинг Changelog (CRITICAL SQL логика)

### Шаблон парсинга для sprint_issues:

```sql
-- 1. Распарсить changelog и найти все действия со спринтами
WITH changelog_events AS (
  SELECT
    i.id as issue_id,
    i.external_id,
    i.external_key,
    (h).id as history_id,
    (h).author.accountId as author_id,
    (h).created as changed_at,
    item->>'field' as field,
    item->>'from' as from_value_id,
    item->>'to' as to_value_id,
    item->>'fromString' as from_value_name,
    item->>'toString' as to_value_name,
    'added'::text as action,
    row_number() over (partition by i.id, item->>'to' order by (h).created desc) as rn
  FROM raw_jira.issues i,
       jsonb_array_elements(i.changelog->'histories') as h,
       jsonb_array_elements(h->'items') as item
  WHERE (item->>'field' = 'Sprint' OR item->>'field' LIKE 'Fix Version%')
    AND item->>'to' IS NOT NULL
    AND item->>'to' != ''
),
-- 2. Распарсить comma-separated values
sprint_ids_to_add AS (
  SELECT
    issue_id,
    external_key,
    changed_at,
    'added' as action,
    trim(val)::text as sprint_id_str,
    author_id
  FROM changelog_events
  CROSS JOIN LATERAL regexp_split_to_table(
    COALESCE(from_value_id, ''), '\s*,\s*'
  ) as val
  WHERE rn = 1  -- только последнее изменение
    AND val ~ '\S'  -- не пустые строки
),
-- 3. Связать с clean_jira объектами
final_state AS (
  SELECT
    si.issue_id,
    s.id as sprint_id,
    sa.changed_at,
    sa.action,
    u.id as user_id
  FROM sprint_ids_to_add sa
  JOIN clean_jira.issues si ON si.external_id = sa.external_key
  JOIN clean_jira.sprints s ON s.external_id = sa.sprint_id_str
  LEFT JOIN clean_jira.jira_users u ON u.external_id = sa.author_id
)
-- 4. Insert
INSERT INTO clean_jira.sprint_issues (sprint_id, issue_id)
SELECT sprint_id, issue_id FROM final_state
WHERE action = 'added'
ON CONFLICT DO UPDATE SET ...
```

---

## 🗺️ ЧАСТЬ 7: DAG Dependencies (Dagster assets)

```
raw_jira_data
├── clean_jira_issues
│   ├── clean_jira_field_keys
│   │   ├── clean_jira_field_values
│   │   └── clean_jira_field_value_changelog  🔴 CRITICAL!
│   ├── clean_jira_sprints
│   │   ├── clean_jira_sprint_issues  🔴 CRITICAL!
│   │   ├── clean_jira_sprint_issues_changelog  🔴 CRITICAL!
│   │   └── clean_jira_sprint_changelog
│   ├── clean_jira_releases
│   │   ├── clean_jira_release_issues
│   │   └── clean_jira_release_issues_changelog
│   ├── clean_jira_boards
│   │   ├── clean_jira_board_columns
│   │   └── clean_jira_board_column_statuses
│   └── (checks & validations)
```

---

## 📌 ЧАСТЬ 8: Приоритеты реализации

### **Phase 1 (CRITICAL для MVP):**

```
🔴 ОЧЕНЬ КРИТИЧНО (для расчета velocity и lead time):
1. sprint_issues           ← из changelog field='Sprint'
2. sprint_issues_changelog ← полная история добавлений/удалений
3. field_values            ← текущие значения полей
4. field_value_changelog   ← история изменений ВСЕХ полей (для metrics calculation!)
```

### **Phase 2 (Нужно для MVP):**

```
🟠 ВАЖНО:
5. sprint_changelog        ← история свойств спринта
6. releases + release_issues ← для релиз-based метрик
7. field_keys              ← справочник полей
8. boards + columns        ← для доски visualization
```

### **Phase 3 (Nice to have):**

```
🟡 ОПЦИОНАЛЬНО:
9. board_column_statuses   ← маппинг статусов к колонкам
10. release_issues_changelog ← история версий
```

---

## 🛠️ ЧАСТЬ 9: Сумма работ по файлам

| Файл | Что добавить | Сложность |
|------|-------------|-----------|
| `pipelines/assets/jira/raw.py` | + 3 ресурса (sprint_issues, versions, board_configurations) | 🟠 Средняя |
| `pipelines/assets/jira/clean.py` | + 10-12 новых assets для всех таблиц | 🔴 Высокая (много SQL) |
| `db/migrations/` | Может потребоваться расширение schema (если raw.py добавляет новые таблицы) | 🟡 Низкая |

---

## ✅ Чеклист реализации

### Raw layer (raw.py):

- [ ] Добавить `get_sprint_issues()` ресурс
  - [ ] Получить все спринты
  - [ ] Для каждого спринта: GET `/rest/agile/1.0/board/{id}/sprint/{sprintId}/issue`
  - [ ] Pagination + error handling

- [ ] Добавить `get_versions()` ресурс
  - [ ] Для каждого проекта: GET `/rest/api/3/project/{key}/versions`
  - [ ] Pagination + error handling

- [ ] Добавить `get_board_configurations()` ресурс
  - [ ] Для каждой доски: GET `/rest/agile/1.0/board/{id}/configuration`
  - [ ] Parse JSONB structure

### Clean layer (clean.py):

- [ ] Расширить `clean_jira_issues()` → extract field_keys
- [ ] Расширить `clean_jira_sprints()` → add sprint_issues + sprint_issues_changelog parsing
- [ ] **🔴 NEW:** `clean_jira_field_keys()` → all field keys from issues
- [ ] **🔴 NEW:** `clean_jira_field_values()` → current field values
- [ ] **🔴 NEW:** `clean_jira_field_value_changelog()` → parse all field changes from changelog
- [ ] **🔴 NEW:** `clean_jira_sprint_issues()` → parse sprint field from changelog
- [ ] **🔴 NEW:** `clean_jira_sprint_issues_changelog()` → history of added/removed
- [ ] **🔴 NEW:** `clean_jira_sprint_changelog()` → sprint property history
- [ ] NEW: `clean_jira_releases()` → from raw_jira.versions
- [ ] NEW: `clean_jira_release_issues()` → parse Fix Version from changelog
- [ ] NEW: `clean_jira_boards()` → from board_configurations
- [ ] NEW: `clean_jira_board_columns()` + `clean_jira_board_column_statuses()`

### Tests:

- [ ] Unit tests для changelog parsing функций
- [ ] Integration tests для всех assets
- [ ] Data quality checks для integrity FK-PK

---

## 🎓 Key Insights из старого Airflow loader

1. **Changelog IS the source of truth** для sprint_issues и field_values
   - API возвращает только текущее состояние
   - История в `issues.changelog` дает complete picture
   - Нужно распарсить и пересчитать final state

2. **Comma-separated values в changelog**
   - Спринты и версии могут быть multiple в одном поле
   - Нужно использовать `regexp_split_to_table()`
   - Trim whitespace!

3. **added/removed actions**
   - Отслеживать both направления (from → removed, to → added)
   - Финальное состояние = последний action по дате
   - Может быть несколько actions по одной паре за историю

4. **Custom fields в changelog**
   - field_keys нужно создавать dynamically из changelog
   - Не все поля есть в raw_jira.issues
   - Парсить `field`, `fieldId`, `from`, `to` из changelog items

5. **User attribution**
   - В changelog есть `author.accountId`
   - Нужно линковать на clean_jira.jira_users для audit trail

---

## 📚 Ссылки

- Jira REST API v3: https://developer.atlassian.com/cloud/jira/platform/rest/v3/intro/
- Agile API: https://developer.atlassian.com/cloud/jira/software/rest/api-group-sprints/
- dlt documentation: https://dlthub.com/docs/

---

**Готово к реализации! Ожидаю DAG структуры для синхронизации с Airflow если нужно.**
