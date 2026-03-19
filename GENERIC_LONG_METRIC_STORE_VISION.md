# Metrics Schema Design: Generic Long Metric Store

## Концепция

Переход от **Semantic Wide Tables** (отдельная `fact_*` таблица на каждую метрику) к **Generic Long Metric Store** (единое хранилище атомарных значений).

**Ключевой принцип:** одна строка `fact_values` = одно число + контекст (кто, когда, по какому правилу).

---

## Полный список таблиц схемы `metrics.*`

```
Конфигурационный слой:
  metrics.definitions         - Логические группы метрик (velocity, lead_time, cfd, ...)
  metrics.grains              - Гранулярность расчёта (issue, sprint, week, day, release)
  metrics.units               - Единицы измерения + маппинг на поле источника (per-project)
  metrics.calculations        - Атомарные вычисления, принадлежащие группам
  metrics.slice_rules         - Правила сегментации (By Issue Type, By Priority, ...)
  metrics.commitment_rules    - Границы расчёта flow-метрик (start/end колонки)

Слой измерений:
  metrics.dim_projects        - Проекты как измерение
  metrics.dim_dates           - Единый календарь

Слой фактов:
  metrics.fact_values         - Единое хранилище всех числовых значений

Презентационный слой:
  metrics.v_facts             - Regular view: fact_values + все dimensions (entry point Metabase)
```

**Итого: 9 таблиц + 1 view.** Новая метрика = строки в `definitions` + `calculations` + Dagster asset. Без ALTER TABLE.

---

## Детальное описание таблиц

### `metrics.definitions`
Логическая группа связанных вычислений. Соответствует одному концепту (Velocity, Lead Time, CFD).

| Колонка | Тип | Описание |
|---------|-----|---------|
| `id` | UUID PK | |
| `metric_code` | TEXT UNIQUE | `velocity`, `lead_time`, `throughput`, `cfd`, `backlog_growth`, `ttm`, `aging`, `flow_efficiency` |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

---

### `metrics.grains`
Справочник гранулярностей. Определяет, на каком уровне агрегируется одна строка `fact_values`.

| Колонка | Тип | Описание |
|---------|-----|---------|
| `id` | UUID PK | |
| `grain_code` | TEXT UNIQUE | `issue`, `sprint`, `week`, `day`, `release` |
| `created_at` | TIMESTAMPTZ | |

---

### `metrics.units`
Единицы измерения с привязкой к источнику данных per-project. Позволяет одной системе работать с проектами, где оценка задач идёт в story points, часах, днях или просто штуках.

Если `project_id IS NULL` - глобальная конфигурация по умолчанию.
При наличии строки с `project_id = X` для того же `unit_code` - она перекрывает глобальную.

| Колонка | Тип | Описание |
|---------|-----|---------|
| `id` | UUID PK | |
| `project_id` | UUID FK nullable → `clean_jira.projects` | NULL = глобальный дефолт |
| `unit_code` | TEXT | `story_points`, `issues`, `days`, `hours`, `percent` |
| `source_field_id` | UUID FK nullable → `clean_jira.field_keys` | Поле источника (для SP = custom field) |
| `source_entity` | TEXT nullable | `clean_jira.issues`, `clean_jira.sprints` - где искать поле |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

UNIQUE: `(project_id, unit_code)`

**Примеры:**
- `project_id=NULL, unit_code='issues'` - по умолчанию throughput считается в штуках (поле не нужно)
- `project_id=PROJ_A, unit_code='story_points', source_field_id=sp_field, source_entity='issues'` - в PROJ_A SP лежат в custom field "customfield_10028"
- `project_id=PROJ_B, unit_code='hours', source_field_id=hours_field, source_entity='issues'` - в PROJ_B оценка в часах

Когда Dagster рассчитывает `velocity_planned_sp` для проекта PROJ_A: ищет `units WHERE unit_code = 'story_points' AND project_id = PROJ_A`, читает `source_field_id` и знает откуда брать число.

---

### `metrics.calculations`
Атомарное вычисление - одно число на одну строку в `fact_values`. Принадлежит одной группе (`definitions`).

| Колонка | Тип | Описание |
|---------|-----|---------|
| `id` | UUID PK | |
| `definition_id` | UUID FK → `definitions` | К какой группе относится |
| `calc_code` | TEXT UNIQUE | `velocity_planned_sp`, `lead_time_days`, `cfd_count`, `throughput_count`, ... |
| `grain_id` | UUID FK → `grains` | Гранулярность этого вычисления |
| `unit_code` | TEXT | `story_points`, `issues`, `days`, `hours`, `percent` - ссылка на `units` по коду |
| `uses_commitment_points` | BOOLEAN DEFAULT false | Нужны ли `commitment_rules` для расчёта |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

`unit_code` - не FK, а ссылка по значению: при расчёте Dagster резолвит конкретную строку из `units` с учётом `project_id`.

---

### `metrics.slice_rules`
Правило сегментации. `target_definition_id IS NULL` - правило применяется ко всем группам.

| Колонка | Тип | Описание |
|---------|-----|---------|
| `id` | UUID PK | |
| `project_id` | UUID FK nullable | NULL = глобальное правило |
| `rule_name` | TEXT | `By Issue Type`, `By Priority`, `By Board Status` |
| `target_definition_id` | UUID FK nullable → `definitions` | NULL = для всех групп метрик |
| `target_definition_name` | TEXT nullable | Денормализовано для читаемости |
| `source_table` | TEXT | `clean_jira.issues`, `clean_jira.board_columns` |
| `group_by_source_column` | TEXT | `issue_type`, `priority`, `status_category` |
| `enabled` | BOOLEAN DEFAULT true | |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

---

### `metrics.commitment_rules`
Границы расчёта для flow-метрик. Определяет, какие колонки доски считаются "началом" и "концом" работы.

| Колонка | Тип | Описание |
|---------|-----|---------|
| `id` | UUID PK | |
| `project_id` | UUID FK nullable | NULL = глобальное правило |
| `board_id` | UUID FK nullable → `clean_jira.boards` | NULL = для всех досок проекта |
| `target_calculation_id` | UUID FK → `calculations` | Для какого вычисления (lead_time_days, flow_efficiency_pct) |
| `target_calculation_name` | TEXT | Денормализовано для аудита |
| `start_column_id` | UUID FK → `clean_jira.board_columns` | Commitment Point: начало |
| `end_column_id` | UUID FK → `clean_jira.board_columns` | Commitment Point: конец |
| `start_column_name_snapshot` | TEXT | Снапшот имени (аудит) |
| `end_column_name_snapshot` | TEXT | Снапшот имени (аудит) |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

---

### `metrics.dim_projects`
Проект как измерение. Связь между внутренним UUID и Jira-ключом.

| Колонка | Тип | Описание |
|---------|-----|---------|
| `id` | UUID PK | |
| `project_id` | UUID FK → `clean_jira.projects` | |
| `project_key` | TEXT | `PROJ`, `CORE` |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

---

### `metrics.dim_dates`
Единый календарь. Заполняется один раз (генератор дат). Нет created_at/updated_at - статичная таблица.

| Колонка | Тип | Описание |
|---------|-----|---------|
| `time_id` | INT PK | YYYYMMDD, например `20260318` |
| `full_date` | DATE | |
| `week_num` | INT | Номер недели в году (ISO) |
| `month_num` | INT | 1-12 |
| `quarter` | INT | 1-4 |
| `year` | INT | |

---

### `metrics.fact_values`
Единое хранилище всех числовых значений. Одна строка = одно атомарное число.

- Строка БЕЗ `slice_rule_id` - базовое значение (по всем задачам, без разбивки).
- Строка С `slice_rule_id` - то же вычисление в разрезе.
- `event_start_at` / `event_end_at` - только для flow-метрик (lead_time, cycle_time, flow_efficiency).
- `entity_type` / `entity_id` - указывают на конкретную сущность (задача, спринт, колонка доски).

| Колонка | Тип | Описание |
|---------|-----|---------|
| `id` | UUID PK | |
| `metric_id` | UUID FK → `calculations` | Какое вычисление |
| `project_agg_id` | UUID FK → `dim_projects` | Проект |
| `time_id` | INT FK → `dim_dates` | Дата события (не дата расчёта) |
| `value` | NUMERIC | Само число |
| `entity_type` | TEXT nullable | `issue`, `sprint`, `week`, `board_column`, `release` |
| `entity_id` | TEXT nullable | Ключ/UUID сущности: `PROJ-123`, sprint UUID, column UUID |
| `event_start_at` | TIMESTAMPTZ nullable | Для flow-метрик: момент входа в commitment zone |
| `event_end_at` | TIMESTAMPTZ nullable | Для flow-метрик: момент выхода |
| `slice_rule_id` | UUID FK nullable → `slice_rules` | NULL = базовое значение |
| `slice_value` | TEXT nullable | `Bug`, `High`, `In Progress` |
| `commitment_rule_id` | UUID FK nullable → `commitment_rules` | Аудит: по каким границам считали |
| `created_at` | TIMESTAMPTZ | Когда строка записана |
| `updated_at` | TIMESTAMPTZ | При пересчёте |

---

### `metrics.v_facts` (regular view)

Entry point для Metabase и любого BI. Non-materialized - всегда актуальна, нет refresh.

Объединяет `fact_values` с:
- `calculations`: `calc_code`, `unit_code`, `uses_commitment_points`
- `definitions`: `metric_code`
- `grains`: `grain_code`
- `dim_projects`: `project_key`
- `dim_dates`: `full_date`, `week_num`, `month_num`, `quarter`, `year`
- `slice_rules` (LEFT JOIN): `rule_name` as `slice_rule_name`

---

## Маппинг метрик: как данные ложатся в `fact_values`

### Lead Time

**Группа:** `lead_time` | **Вычисление:** `lead_time_days` | **grain:** `issue` | **unit:** `days`

Одна строка на завершённую задачу. `event_start_at` и `event_end_at` обязательны - это commitment timestamps.

```
metric_id        = calculations.id (calc_code='lead_time_days')
project_agg_id   = dim_projects.id
time_id          = 20260306  ← дата когда задача завершилась (Done)
value            = 5.0       ← дней
entity_type      = 'issue'
entity_id        = 'PROJ-123'
event_start_at   = '2026-03-01 09:00:00'  ← задача попала в "In Progress"
event_end_at     = '2026-03-06 14:30:00'  ← задача вышла в "Done"
commitment_rule_id = commitment_rules.id  ← аудит по каким колонкам считали
slice_rule_id    = NULL  ← base строка
```

Дополнительно для каждого активного `slice_rule`: те же поля, плюс `slice_rule_id + slice_value = 'Bug'`.

**Источник:** `clean_jira.issue_status_changelog` + `commitment_rules` (определяют start/end колонки).

---

### Velocity

**Группа:** `velocity` | **grain:** `sprint`

4 вычисления - 4 строки на спринт:

| calc_code | entity_type | entity_id | value | unit |
|-----------|-------------|-----------|-------|------|
| `velocity_planned_sp` | `sprint` | sprint UUID | 34 | story_points |
| `velocity_completed_sp` | `sprint` | sprint UUID | 28 | story_points |
| `velocity_planned_count` | `sprint` | sprint UUID | 12 | issues |
| `velocity_completed_count` | `sprint` | sprint UUID | 10 | issues |

`time_id` = дата завершения спринта. `event_start_at/end_at = NULL`.

Единицы (`story_points`) резолвятся через `units WHERE unit_code='story_points' AND project_id=X` - Dagster знает из какого custom field читать.

Срезы (`slice_rule_id` IS NOT NULL): дополнительные строки для `velocity_completed_sp` по Issue Type = 'Bug', 'Story' и т.д.

**Источник:** `clean_jira.sprints` + `sprint_issues` + `units` (какой field для SP) + `issue_status_changelog` (кто завершил).

---

### Throughput

**Группа:** `throughput` | **Вычисление:** `throughput_count` | **grain:** `week` | **unit:** `issues`

Одна строка на неделю на проект. Срезы - дополнительные строки по Issue Type.

```
metric_id        = calculations.id (calc_code='throughput_count')
time_id          = 20260316  ← Monday (начало недели)
value            = 15        ← задач завершено за неделю
entity_type      = 'week'
entity_id        = '2026-03-16'
event_start_at   = NULL
slice_rule_id    = NULL (base)
```

---

### CFD (Cumulative Flow Diagram)

**Группа:** `cfd` | **Вычисление:** `cfd_count` | **grain:** `day` | **unit:** `issues`

CFD отличается от других метрик: **"статус доски" - это первичное измерение**, а не срез.
Решение: `entity_type = 'board_column'`, `entity_id` = UUID колонки доски.
`slice_rule_id = NULL` - срезы не используются.

Одна строка = (проект, день, колонка доски) → количество задач.

```
metric_id        = calculations.id (calc_code='cfd_count')
project_agg_id   = dim_projects.id
time_id          = 20260318  ← дата снапшота
value            = 42        ← задач в этом статусе на эту дату
entity_type      = 'board_column'
entity_id        = 'uuid-of-in-progress-column'  ← UUID колонки из clean_jira.board_columns
event_start_at   = NULL
slice_rule_id    = NULL
```

Запрос CFD для отображения:
```sql
SELECT
    dt.full_date,
    bc.name      AS status_name,
    bc.position  AS column_order,
    fv.value     AS issue_count
FROM metrics.fact_values fv
JOIN metrics.calculations c   ON fv.metric_id = c.id
JOIN metrics.dim_dates dt     ON fv.time_id = dt.time_id
JOIN metrics.dim_projects dp  ON fv.project_agg_id = dp.id
JOIN clean_jira.board_columns bc ON fv.entity_id::uuid = bc.id
WHERE c.calc_code = 'cfd_count'
  AND dp.project_key = 'PROJ'
ORDER BY dt.full_date, bc.position;
```

`bc.position` даёт правильный порядок колонок для CFD.

---

### Backlog Growth

**Группа:** `backlog_growth` | **grain:** `day`

4 вычисления - 4 строки на день на проект:

| calc_code | value | unit | Описание |
|-----------|-------|------|---------|
| `backlog_size` | 150 | issues | Всего задач в бэклоге |
| `backlog_created` | 5 | issues | Создано сегодня |
| `backlog_resolved` | 3 | issues | Закрыто сегодня |
| `backlog_net_growth` | 2 | issues | created - resolved |

`entity_type = NULL`, `entity_id = NULL` - нет привязки к конкретной задаче.

---

### Time to Market (TTM)

**Группа:** `ttm` | **Вычисление:** `ttm_days` | **grain:** `issue` | **unit:** `days`

Одна строка на выпущенную задачу. `event_start_at` = дата создания задачи, `event_end_at` = дата релиза.

```
time_id       = дата релиза
value         = 45.0  (дней)
entity_type   = 'issue'
entity_id     = 'PROJ-123'
event_start_at = '2026-01-31'  ← jira_created_at
event_end_at   = '2026-03-17'  ← дата релиза
```

---

### Work Item Aging

**Группа:** `aging` | **Вычисление:** `aging_days` | **grain:** `issue` | **unit:** `days`

Ежедневный снапшот активных задач. Одна строка на активную задачу на день.

```
time_id       = сегодняшняя дата (дата снапшота)
value         = 12  (дней в текущем статусе)
entity_type   = 'issue'
entity_id     = 'PROJ-456'
event_start_at = '2026-03-07'  ← когда задача вошла в текущий статус
event_end_at   = NULL          ← ещё не вышла
```

---

### Flow Efficiency

**Группа:** `flow_efficiency` | **grain:** `issue`

3 вычисления - 3 строки на завершённую задачу:

| calc_code | value | unit | Описание |
|-----------|-------|------|---------|
| `flow_active_days` | 3.0 | days | Дней активной работы |
| `flow_wait_days` | 7.0 | days | Дней ожидания |
| `flow_efficiency_pct` | 30.0 | percent | active / (active + wait) * 100 |

`event_start_at/end_at` - те же commitment timestamps что и у lead_time (определяются через `commitment_rules`).

---

## Правила работы системы

**Правило 1 — Atomic Single Value:**
Каждая строка `fact_values` содержит ровно одно число. Velocity = 4 строки (4 вычисления). Flow Efficiency = 3 строки.

**Правило 2 — Base + Slices:**
Dagster asset для каждого расчёта пишет:
1. Base строки (`slice_rule_id = NULL`) - агрегат без разбивки
2. По одному набору slice строк на каждое активное `slice_rules`

**Правило 3 — CFD без слайсов:**
CFD использует `entity_type = 'board_column'` как первичное измерение. `slice_rule_id` для CFD всегда NULL.

**Правило 4 — event_start/end только для flow-метрик:**
`event_start_at` и `event_end_at` заполняются только для метрик с `uses_commitment_points = true`: `lead_time_days`, `cycle_time_days`, `flow_active_days`, `flow_wait_days`, `flow_efficiency_pct`, `ttm_days`, `aging_days`.

**Правило 5 — time_id = дата события, не расчёта:**
`time_id` = дата когда произошло событие (задача завершилась, спринт закончился, день снапшота).
`created_at` = когда Dagster записал строку.

**Правило 6 — Idempotency:**
При повторном запуске Dagster делает `DELETE WHERE metric_id = X AND project_agg_id = Y AND time_id IN (...)` перед INSERT.

**Правило 7 — Units per project:**
Dagster резолвит `units` для проекта: сначала ищет `project_id = X`, при отсутствии берёт `project_id = NULL` (глобальный дефолт). Это позволяет проектам с часами и проектам со story points работать с одним и тем же Dagster asset `calculate_velocity`.

---

## Стратегия Metabase и BI

**БД:** единая `metrics.v_facts` (regular view) - entry point. PM подключает Metabase к этой view.

**Metabase Models** (saved questions как виртуальные таблицы):

| Model | Фильтр | Изменяет |
|-------|--------|---------|
| "Velocity Dashboard" | `metric_code = 'velocity' AND slice_rule_id IS NULL` | PM в UI |
| "Lead Time Distribution" | `calc_code = 'lead_time_days'` | PM в UI |
| "CFD" | `calc_code = 'cfd_count'` + JOIN на board_columns | PM в UI |
| "Throughput by Type" | `calc_code = 'throughput_count' AND slice_rule_id IS NOT NULL` | PM в UI |

Изменение отображения = изменение Metabase Model в UI. Нет SQL миграций. Нет code deployments.

---

## Open Source: точки расширения

| Что хочет пользователь | Как делает |
|------------------------|-----------|
| Добавить метрику | Строки в `definitions` + `calculations` + Dagster asset |
| Добавить источник (GitLab) | Новый `definitions.metric_code` с новым Dagster asset |
| Настроить оценку задач | Строка в `units` через Admin API |
| Добавить кастомный срез | Строка в `slice_rules` через Admin API |
| Изменить границы Lead Time | Строка в `commitment_rules` через Admin API |
| Настроить CFD по другой доске | Новый расчёт с другим `board_id` в commitment_rules |
