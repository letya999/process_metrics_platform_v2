# План развития системы метрик (Future Metrics Roadmap)

Этот документ описывает структуру и логику системы аналитики процессов разработки.

## 1. Конфигурация (Configuration Layer)

Система управляется через таблицы правил, позволяя гибко настраивать расчет метрик без изменения кода.

### 1.1. Правила Срезов (`metric_slice_rules`)
Определяет, как сегментируются метрики. Позволяет создавать срезы (slices) для метрик по значениям произвольных полей (Project, Issue Type, Priority и др.).

**Архитектура:**
*   **Глобальные правила:** Правила с `project_id = NULL` применяются ко всем проектам.
*   **Правила по умолчанию:** Правила с `target_metric_table = 'default'` применяются ко всем поддерживаемым метрикам (например, "By Issue Type").
*   **Таблицы срезов:** Для каждой метрики создается таблица `*_slices` (во множественном числе), куда пишутся данные.

**Реализованные таблицы срезов:**
*   `fact_velocity_slices` (По спринтам)
*   `fact_throughput_slices` (По неделям)
*   `fact_backlog_growth_slices` (По периодам)
*   `fact_lead_time_slices` (По задачам)
*   `fact_time_to_market_slices` (По задачам)
*   `fact_flow_efficiency_slices` (По задачам)
*   `fact_work_item_aging_slices` (По задачам)

**Структура таблицы правил (`metric_slice_rules`):**
*   `id` (PK): UUID
*   `project_id`: Ссылка на проект (FK). NULL = Глобальное правило.
*   `target_metric_table`: Имя основной таблицы метрики (или 'default').
*   `slice_table_name`: Имя таблицы среза (опционально).
*   `rule_name`: Название правила (например, "By Issue Type", "By Priority").
*   `source_table`: Таблица-источник (например, `clean_jira.issues`).
*   `group_by_column`: Колонка группировки (например, `issue_type`, `priority`).
*   `filter_condition`: Опциональный SQL-фильтр (например, `issue_type != 'Epic'`).
*   `enabled`: Флаг активности.

### 1.2. Общая структура таблиц срезов (`*_slices`)
Все таблицы срезов следуют единому паттерну. В них **убраны хардкодные колонки измерений** (например, `issue_type`), вместо этого используется связка `slice_rule_name` + `slice_value`.

**Общие колонки:**
*   `id` (PK): UUID
*   `project_id`: UUID (FK)
*   `slice_rule_name`: Название примененного правила (например, "By Issue Type").
*   `slice_value`: Значение среза (например, "Bug", "High").
*   `created_at`: Timestamp.

**Специфичные колонки (примеры):**
*   **Velocity Slices:** `sprint_id`, `planned_points`, `completed_points`.
*   **Throughput Slices:** `completed_date` (week start), `issues_completed`, `avg_lead_time_days`.
*   **Lead Time Slices:** `issue_id`, `issue_key`, `lead_time_days`, `commitment_start/end`.
*   **TTM Slices:** `issue_id`, `issue_key`, `time_to_market_days`, `released_at`.

### 1.3. Правила Границ Процесса (`metrics_commitment_points_rules`)
Позволяет для каждой метрики и доски переопределить границы "начала" и "конца" работ (Lead Time vs Cycle Time).

**Структура таблицы:**
*   `id` (PK): UUID
*   `project_id`: Ссылка на проект (FK)
*   `board_id`: Ссылка на доску (FK)
*   `target_metric_table`: (например, `fact_lead_time`)
*   `start_column_name`: Колонка начала (Commitment Point 1)
*   `end_column_name`: Колонка конца (Commitment Point 2)

---

## 2. Метрики Процесса (Process Metrics)

### 2.1. Lead Time & Cycle Time
Время прохождения процесса.
*   **Базовая таблица:** `metrics.fact_lead_time`
    *   `issue_id`, `lead_time_days`, `commitment_start_at`, `commitment_end_at`.
*   **Срезы:** `metrics.fact_lead_time_slices`
    *   Содержит те же данные, но дублированные для каждого сработавшего правила среза (`slice_rule_name`, `slice_value`).
*   **Гистограмма:** `metrics.fact_lead_time_bins`
    *   Агрегированное распределение (бины) для построения гистограмм.

### 2.2. Velocity
Скорость команды по спринтам.
*   **Базовая таблица:** `metrics.fact_velocity`
    *   `sprint_id`, `planned_issues`, `completed_issues`, `planned_sp`, `completed_sp`.
*   **Срезы:** `metrics.fact_velocity_slices`
    *   Позволяет смотреть Velocity, например, только по багам или только по фичам.

### 2.3. Throughput
Пропускная способность (задачи в неделю).
*   **Базовая таблица:** `metrics.fact_throughput`
    *   `week_start_date`, `issue_type` (Legacy), `issues_completed`.
*   **Срезы:** `metrics.fact_throughput_slices`
    *   `completed_date`, `slice_rule_name`, `slice_value`, `issues_completed`.

### 2.4. Work Item Age (Aging)
Возраст активных задач.
*   **Базовая таблица:** `metrics.fact_work_item_aging`
    *   `issue_id`, `current_status`, `age_days`.
*   **Срезы:** `metrics.fact_work_item_aging_slices`

### 2.5. Flow Efficiency
Эффективность потока (Active vs Wait time).
*   **Базовая таблица:** `metrics.fact_flow_efficiency`
    *   `issue_id`, `active_days`, `wait_days`, `efficiency_pct`.
*   **Срезы:** `metrics.fact_flow_efficiency_slices`

### 2.6. Time To Market (TTM)
Время от создания до релиза.
*   **Базовая таблица:** `metrics.fact_time_to_market`
    *   `issue_id`, `time_to_market_days`, `released_at`.
*   **Срезы:** `metrics.fact_time_to_market_slices`

### 2.7. Backlog Growth
Динамика бэклога.
*   **Срезы:** `metrics.fact_backlog_growth_slices`
    *   `period_start`, `period_type`, `created_count`, `completed_count`, `net_growth`.

---

## 3. Метрики Качества и Планирования (Future)

Разделы, планируемые к реализации:
*   Sprint Plan Efficiency (`fact_sprint_efficiency`)
*   Release Plan Efficiency (`fact_release_efficiency`)
*   Bug Density (`fact_sprint_bug_density`, `fact_issue_bug_density`)
*   Burndown/Burnup Charts (`fact_sprint_burndown`, `fact_scope_burnup`)
