# Vision: Metric Store Architecture (GLMS)

Этот документ описывает текущее состояние (проблемы реализации) и целевое видение архитектуры метрик в проекте.

## 1. AS IS: Текущее состояние (Проблемы и ограничения)
Система формально использует `metrics.fact_values`, но наполнение данных остается скудным ("Short Store" вместо "Long Store").

| Группа (Definition) | Расчеты (Calculations) | Entity ID / Type | Проблемы (Issues) |
| :--- | :--- | :--- | :--- |
| **velocity** | `planned_sp`, `completed_sp`, `planned_count`, `completed_count` | `sprint_id` / `sprint` | Поля `event_start_at` и `event_end_at` пусты (NULL). Нет `context_json` — в Metabase видны только ID спринтов и числа. |
| **lead_time** | `lead_time_days` | `issue_id` / `issue` | Используется только один `Calculation`. `cycle_time` и `wait_time` не сохраняются как отдельные факты. |
| **aging** | `age_days` | `issue_id` / `issue` | Срез делается только по общему возрасту. Нет историчности по нахождению в конкретных статусах. |
| **slicing** | Все вышеуказанные | `slice_rule_id` | Слайсинг работает, но без контекста в `fact_values` невозможно понять, что такое `slice_value='10005'`, не заглядывая в справочники Jira. |

**Главная проблема:** Таблица `fact_values` сейчас — это "черный ящик" из UUID. Без массивных JOIN-ов с `clean_jira` данные нечитаемы для человека и BI.

---

## 2. TO BE: Целевое видение (Rich Long Store)
Каждая строка в `metrics.fact_values` должна быть самодостаточной для визуализации и фильтрации.

### Матрица метрик (Целевая)
| Definition | Calculation (metric_id) | Entity Type | Commitment / Events | Context JSON (Обязательно) |
| :--- | :--- | :--- | :--- | :--- |
| **velocity** | `planned_sp`, `actual_sp`, `predictability` | `sprint` | Даты начала/конца спринта | `{"name": "Sprint 24", "goal": "...", "board": "Core"}` |
| **lead_time** | `lead_time_days`, `cycle_time_days`, `wait_time_days` | `issue` | `event_start`: Created. `event_end`: Resolved. | `{"key": "PROJ-1", "type": "Bug", "priority": "High"}` |
| **status_analytics**| `status_duration_days` | `issue` | Вход/выход из конкретного статуса | `{"status_name": "Review", "category": "In Progress"}` |
| **throughput** | `throughput_count` | `project` | Дата Resolution (`event_end_at`) | `{"issue_type": "Story", "resolution": "Fixed"}` |
| **aging** | `current_age_days`, `current_status_age` | `issue` | Дата замера (Snapshot) | `{"key": "PROJ-2", "status": "In Dev", "stale_days": 5}` |
| **flow_eff** | `efficiency_pct`, `active_days`, `wait_days` | `issue` | Ссылка на `commitment_rule_id` (маппинг) | `{"work_statuses": ["Dev", "QA"], "wait_statuses": ["Todo"]}` |

---

## 3. Архитектурные принципы

1.  **Один Definition -> Много Calculations:** Группа "Lead Time" порождает факты "Lead Time Days", "Cycle Time Days" и "Wait Time Days".
2.  **Context JSON — это не опция:** Каждая запись обязана содержать человекочитаемые атрибуты (key, name, type). Это цена скорости BI-слоя.
3.  **Commitments управляют расчетом:** Точки `event_start_at` и `event_end_at` всегда вычисляются на основе `metrics.commitment_rules`, а не хардкода.
4.  **Единое хранилище:** Полный отказ от широких таблиц (`fact_velocity` и т.д.) в пользу `fact_values`.
5.  **Юниты (Units):** Все расчеты ссылаются на `metrics.units`, чтобы знать, какое поле Jira считать за Story Points или какие статусы считать активными.
