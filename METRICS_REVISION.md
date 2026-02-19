# Ревизия метрик и данных

Этот документ описывает текущее состояние конвейеров данных (pipelines) и схемы базы данных (db), охватывая расчет метрик, соответствующие ассеты Dagster и целевые таблицы.

## Обзор архитектуры

Система использует **Dagster** для оркестрации расчетов.
1. **Raw/Clean Layer**: Данные извлекаются из источников (Jira) в схему `clean_jira` (определено в `db/schemas/clean_jira_schema.sql`).
2. **Metrics Layer**: Ассеты Dagster (`pipelines/assets/metrics/`) читают данные из `clean_jira` и рассчитывают метрики, сохраняя их в схему `metrics` (таблицы `fact_*`).

## Карта метрик

Ниже приведена таблица соответствия между аналитическими областями, ассетами, логикой расчета и целевыми таблицами.

| Область / Метрика | Ассет Dagster | Логика (Python) | Целевые таблицы (Schema: `metrics`) | Основные колонки |
| :--- | :--- | :--- | :--- | :--- |
| **Lead Time** | `calculate_lead_time` | `pipelines.calculations.lead_time` | `fact_lead_time` | `issue_id`, `lead_time_days`, `commitment_start_at`, `commitment_end_at` |
| | | | `fact_lead_time_slice` | `issue_type`, `slice_dim`, `avg_lead_time_days`, `p90_lead_time_days` |
| | | | `fact_lead_time_bins` | `bin_number`, `tickets_count` |
| | | | `fact_lead_time_bins_slice` | `issue_type`, `bin_number`, `tickets_count` |
| **Velocity** | `calculate_velocity` | `pipelines.calculations.velocity` | `fact_velocity` | `iteration_id`, `planned_story_points`, `completed_story_points`, `completion_rate` |
| | | | `fact_velocity_slice` | `issue_type`, `slice_dim`, `planned_...`, `completed_...` |
| **Throughput** | `calculate_throughput` | `pipelines.calculations.throughput` | `fact_throughput` | `week_start_date`, `issue_type`, `issues_completed`, `avg_lead_time_days` |
| | | | `fact_throughput_aggregates` | `avg_weekly_throughput`, `min_weekly`, `max_weekly` |
| **Cumulative Flow** | `calculate_cumulative_flow_diagram` | `pipelines.calculations.cumulative_flow` | `fact_cfd` | `date`, `status_name`, `issue_count`, `column_position` |
| | | | `fact_cfd_aggregates` | `status_name`, `avg_daily_count`, `trend` |
| **Backlog Health** | `calculate_backlog_health` | `pipelines.calculations.backlog_health` | `fact_backlog_health` | `total_backlog_size`, `avg_age_days`, `stale_issues_count` |
| | | | `fact_backlog_distribution` | `issue_type`, `priority`, `percentage` |
| | | | `fact_backlog_age_distribution` | `age_bucket`, `percentage` |
| **Time to Market** | `calculate_time_to_market` | `pipelines.calculations.time_to_market` | `fact_time_to_market` | `released_at`, `time_to_market_days` |
| | | | `fact_ttm_aggregates` | `avg_ttm_days`, `median_ttm_days`, `p90_ttm_days` |
| | | | `fact_release_cadence` | `avg_days_between_releases`, `releases_per_month` |
| **Advanced / Pro** | `calculate_advanced_metrics` | `pipelines.calculations.aging` | `fact_work_item_aging` | `issue_id`, `age_days`, `age_in_status_days`, `current_status_id` |
| | | `pipelines.calculations.flow_efficiency` | `fact_flow_efficiency` | `active_days`, `wait_days`, `flow_efficiency_pct` |
| | | `pipelines.calculations.control_chart` | `fact_control_chart` | `rolling_mean`, `rolling_std`, `ucl_3sigma`, `is_outlier` |
| | | *(Not implemented)* | `fact_lead_time_trend` | *Таблица создана в миграции 0013, но расчет в ассете отсутствует* |

> **Примечание**: Логика расчета `Lead Time Trend` существует в `pipelines/calculations/lead_time_trend.py`, но не подключена в ассете `calculate_advanced_metrics` (см. `pipelines/assets/metrics/advanced.py`), поэтому таблица `fact_lead_time_trend` остается пустой.

## Джобы (Jobs) и Расписания (Schedules)

Определены в `pipelines/jobs/schedules.py`.

*   **`jira_sync_job`** (Schedule: `0 6 * * *` - Daily UTC): Полный цикл. Запускает группы ассетов `jira_raw`, `jira_clean` и `metrics`.
*   **`metrics_refresh_job`** (Schedule: `0 * * * *` - Hourly): Пересчитывает только метрики (группа `metrics`).
*   **Recalculation Jobs** (запускаются вручную): Отдельные джобы для пересчета конкретных метрик (напр. `recalculate_lead_time_job`, `recalculate_velocity_job`).

## Структура Базы Данных (Schema: `metrics`)

Все целевые таблицы находятся в схеме `metrics`. Их структура определяется миграциями (основные: `0011`, `0012`, `0013`).

### Основные таблицы фактов

*   **`fact_lead_time`**: Базовая таблица Lead Time по каждому тикету.
    *   `id` (PK), `project_id`, `issue_id`, `lead_time_days`, `commitment_start_at`, `commitment_end_at`
*   **`fact_velocity`**: Velocity по спринтам.
    *   `id` (PK), `project_id`, `iteration_id`, `planned_story_points`, `completed_story_points`
*   **`fact_throughput`**: Пропускная способность (по неделям).
    *   `project_id`, `week_start_date`, `issue_type`, `issues_completed`
*   **`fact_cfd`**: Снэпшоты количества задач в статусах по дням.
    *   `project_id`, `date`, `status_name`, `issue_count`
*   **`fact_time_to_market`**: Время от создания до релиза.
    *   `issue_id`, `released_at`, `time_to_market_days`

### Таблицы срезов и агрегатов

*   **Slices**: `fact_lead_time_slice`, `fact_velocity_slice`, `fact_lead_time_bins`, `fact_lead_time_bins_slice`. Содержат предрассчитанные агрегаты по типам задач и другим измерениям.
*   **Aggregates**: `fact_throughput_aggregates`, `fact_cfd_aggregates`, `fact_ttm_aggregates`. Содержат сводную статистику (средние, медианы, процентили) для быстрого отображения на дашбордах.

### Pro / Advanced Metrics

*   **`fact_work_item_aging`**: Текущий возраст активных задач.
*   **`fact_flow_efficiency`**: Соотношение времени работы к времени ожидания.
*   **`fact_control_chart`**: Скользящие средние и границы (sigma) для выявления выбросов.
*   **`fact_lead_time_trend`**: *(Пустая)* Должна содержать тренды Lead Time (недельные/месячные P50/P85).

---
*Документ автоматически сгенерирован на основе анализа кода и структуры БД.*
