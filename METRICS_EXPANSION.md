# Расширенный каталог метрик (Process Metrics Platform v2)

В данном документе представлена детальная спецификация для реализации 22 новых метрик. Каждая метрика описана в терминах структуры данных проекта.

## Новые группы метрик (metrics.definitions)
Для реализации расчетов необходимо добавить в таблицу `metrics.definitions` следующие коды:
- `sprint_health`: Здоровье и стабильность спринта.
- `flow_dynamics`: Динамика переходов и активность.
- `quality`: Качество продукта и дефекты.
- `delivery`: Релизные метрики и вехи.
- `waste`: Потери (отмены, брошенная работа).
- `estimation`: Качество и волатильность оценок.

## Спецификация метрик

| # | Calculation | Definition (metric_code) | Units | Grains | Коммитментсы (commitment_rules) | Контекст JSON | Что означает | Какие ивенты используются | Как считается |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| 1 | `sprint_added_issues_count` | `sprint_health` | `issues` | sprint | `-` | `{"iteration_id": "123", "iteration_name": "Sprint 1"}` | Изменение плана спринта "на лету" | `issue_changelog` | `count(issue)` где `change_time(sprint added) > sprint_start_date` |
| 2 | `sprint_added_sp_sum` | `sprint_health` | `story_points` | sprint | `-` | `{"iteration_id": "123", "iteration_name": "Sprint 1"}` | Вес незапланированных работ | `issue_changelog`, поле из `metrics.units` | `sum(value)` для задач из п.1. Поле оценки берется по `unit_code='story_points'`. |
| 3 | `sprint_removed_issues_count` | `sprint_health` | `issues` | sprint | `-` | `{"iteration_id": "123", "iteration_name": "Sprint 1"}` | Дескоуп спринта | `issue_changelog` | `count(issue)` где `change_time(sprint removed) < sprint_end_date` |
| 4 | `sprint_removed_sp_sum` | `sprint_health` | `story_points` | sprint | `-` | `{"iteration_id": "123", "iteration_name": "Sprint 1"}` | Объем дескоупа в единицах оценки | `issue_changelog`, поле из `metrics.units` | `sum(value)` для задач из п.3. Поле оценки берется по `unit_code='story_points'`. |
| 5 | `sprint_spillover_count` | `sprint_health` | `issues` | sprint | `-` | `{"iteration_id": "123", "iteration_name": "Sprint 1"}` | Хвосты и плохая декомпозиция | `issues.sprint_ids` | `count(issue)` где `array_length(sprint_ids) > 1` в текущем спринте |
| 6 | `sprint_burndown_remaining_sp` | `sprint_health` | `story_points` | sprint | `-` | `{"iteration_id": "123", "iteration_name": "Sprint 1"}` | **Остаток** работ до нуля в конце спринта | `issue_changelog` (status), `metrics.units` | `Total_Planned_SP - Cumulative_Sum(Completed_SP_up_to_day_X)`. Линия стремится к 0. |
| 7 | `activation_velocity_pct` | `sprint_health` | `percent` | sprint | `commitments.start` | `{"iteration_id": "123", "iteration_name": "Sprint 1", "initial_status": "To Do"}` | **Скорость активации**: Процент SP от общего плана, которые команда перевела из "To Do" в работу на N-й день спринта. Позволяет увидеть "раскачку" или застой в начале. | `issue_changelog` (status), `metrics.units` | `(Sum(SP_moved_from_initial_on_day_X) / Total_Planned_Sprint_SP) * 100`. Кумулятивно по дням спринта. |
| 8 | `daily_status_entry_count` | `flow_dynamics` | `issues` | sprint | `-` | `{"iteration_id": "123", "iteration_name": "Sprint 1", "target_status": "In Progress"}` | **Интенсивность потока**: Сколько задач физически "входит" в выбранный статус каждый день. Показывает ритмичность работы команды без привязки к SP. | `issue_changelog` (status) | `count(issue_id)` где `change_time` попал в конкретный день, а `to_status` = `target_status`. |
| 9 | `input_flow_weekly` | `throughput` | `issues` | week | `commitments.start` | `{"iso_week": "2026-W12"}` | Скорость входящего потока в работу | `issue_changelog` (status) | `count(issue)` за неделю при переходе в `commitment_start` |
| 10 | `defect_density_by_type` | `quality` | `ratio` | sprint | `-` | `{"iteration_id": "123", "iteration_name": "Sprint 1"}` | **Универсальное ратио**: Отношение одного типа задач к другому. Настраивается через `calculation_settings`. | `issues.issue_type` | `count(type=settings.numerator) / count(type=settings.denominator)`. Пример: Баги на Стори. |
| 11 | `backflow_column_rate` | `quality` | `percent` | sprint | `commitments.start` | `{"iteration_id": "123", "iteration_name": "Sprint 1"}` | **Процент возвратов**: Доля переходов, при которых задача вернулась в колонку с меньшим `position` (например, из QA в Dev). Сигнал о проблемах качества/описания. | `issue_changelog` (status), `board_columns` | `(count(transitions_where_new_pos < old_pos) / total_transitions) * 100` за период. |
| 12 | `release_burnup_sp` | `delivery` | `story_points` | project | `-` | `{"version_name": "v1.1", "release_date": "2026-04-01"}` | **Прогресс релиза**: Линия накопленного объема (Scope) vs Линия завершенных работ (Done). Идет снизу вверх к общей сумме. | `issues.fix_versions`, `changelog` | Две линии: 1. `Cumulative_Total_SP_in_Version`, 2. `Cumulative_Done_SP`. |
| 13 | `issue_lifetime_days` | `cycle_time` | `days` | issue | `commitments.end` | `{"key": "PROJ-1", "type": "Story"}` | **Время существования**: Полный цикл от `created` до финального `Done`. | `issues.created`, `changelog` | `date_diff(end_date, created_date)` |
| 14 | `cancellation_rate_weekly` | `waste` | `issues` | week | `commitments.end` | `{"iso_week": "2026-W12", "cancelled_status": "Rejected"}` | Уровень "брошенной" работы | `issue_changelog` (status) | `count(issue)` в статусе отмены за неделю |
| 15 | `cycle_time_custom` | `cycle_time` | `days` | issue | `commitments.start`, `commitments.end` | `{"key": "PROJ-1", "type": "Story", "start": "In Dev", "end": "In QA"}` | Скорость прохождения конкретных этапов | `issue_changelog` (status) | `date_diff(custom_end_date, custom_start_date)` |
| 16 | `estimate_volatility_abs` | `estimation` | `story_points` | issue | `-` | `{"key": "PROJ-1", "type": "Story"}` | Стабильность оценки/понимание задачи | `issue_changelog`, поле из `metrics.units` | `abs(final_value - initial_value)` по каждой задаче. |
| 17 | `blocked_time_total` | `aging` | `hours` | issue | `-` | `{"key": "PROJ-1", "type": "Story", "flag_name": "blocked"}` | Потери на внешние зависимости/преграды | `issue_changelog` (field `blocked`) | Сумма `time_diff` интервалов, где `blocked=true` |
| 18 | `field_value_sprint_pct` | `sprint_health` | `percent` | sprint | `-` | `{"iteration_id": "123", "iteration_name": "Sprint 1", "field": "priority", "value": "Highest"}` | Структура работ в спринте | `issues` (fields) | `(count(issue with field=X) / total_in_sprint) * 100` |
| 19 | `field_change_count` | `flow_dynamics` | `issues` | sprint | `-` | `{"iteration_id": "123", "iteration_name": "Sprint 1", "field": "assignee"}` | Нестабильность (чехарда с полями) | `issue_changelog` (field) | `count(change_events)` для поля в рамках дат спринта |
| 20 | `stale_days` | `aging` | `days` | issue | `-` | `{"key": "PROJ-1", "type": "Story", "status": "In Dev"}` | Выявление "зависших" задач | `issues.updated` | `date_diff(now, last_update_date)` |
| 21 | `epic_delivery_time` | `ttm` | `days` | issue (parent) | `commitments.start`, `commitments.end` | `{"key": "PROJ-EPIC-1", "type": "Epic"}` | Реальное время поставки крупной фичи | `issues.parent_id`, `changelog` | `max(children.end_date) - min(children.start_date)` |
| 22 | `unestimated_closed_count` | `sprint_health` | `issues` | sprint | `commitments.end` | `{"iteration_id": "123", "iteration_name": "Sprint 1"}` | "Темная материя": закрыто без оценки | `changelog`, поле из `metrics.units` | `count(issue)` где `status=Done` AND (`sp` is null OR `sp`=0) |
