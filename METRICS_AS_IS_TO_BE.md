# Метрики платформы: AS-IS и TO-BE

## 1) AS-IS (что есть сейчас)

| Дифинишн | Калькулейшнс | Юнитс | Энтитис | Грейнс | Коммитментсы | Контекст JSON | Что означает | Какие ивенты используются для расчета | Как считается |
|---|---|---|---|---|---|---|---|---|---|
| velocity | velocity_planned_sp, velocity_completed_sp, velocity_planned_count, velocity_completed_count | story_points, issues | sprint (entity_id=sprint_id) | sprint | В основном не используются; event_start_at/event_end_at часто пустые | Часто отсутствует/минимальный | План vs факт по спринту в SP и в количестве задач | Sprint start/end, membership issue в спринте, статус на конец спринта | Агрегация задач спринта: суммируются SP и counts, затем completion rate |
| lead_time | lead_time_days | days | issue | issue | Используются через commitment_rules (start/end колонки) | Ограниченный | Время от входа в стартовую точку потока до завершения | Переход issue в start column и в end column (board workflow) | Разница между event_end_at и event_start_at в днях |
| throughput | throughput_count | issues | project/week bucket | week | Нет | Ограниченный | Количество завершенных задач за неделю | Resolution/Done события, дата завершения | Count задач, сгруппированный по ISO-week |
| cfd | cfd_count | issues | board_column/status | day | Нет | Ограниченный | Снимок количества задач по колонкам статуса на день | Состояние issue в колонке на дату среза | Daily snapshot count по status/column |
| backlog_growth | backlog_size, backlog_created, backlog_resolved, backlog_net_growth, backlog_avg_age_days, backlog_stale_count, backlog_oldest_days, backlog_stale_pct | issues, days, percent | project | day | Нет | Ограниченный | Рост/здоровье бэклога по дням | Created, Resolved и open state на дату | Daily формулы: size, created-resolved, age/stale агрегаты |
| ttm | ttm_days | days | issue/release path | issue | Используются (по flow milestones) | Ограниченный | Time-to-market от начала работы до поставки/релиза | Workflow transitions + release/deploy marker | Разница между стартовым milestone и release milestone |
| aging | aging_days | days | issue | issue | Частично используются | Ограниченный | Возраст незавершенной задачи | Created + snapshot date (или last status change) | Текущее время жизни issue до текущей даты/среза |
| flow_efficiency | flow_active_days, flow_wait_days, flow_efficiency_pct | days, percent | issue | issue | Используются | Ограниченный | Доля активного времени в общем времени потока | Переходы по статусам, разделение active vs wait | efficiency_pct = active_days / (active_days + wait_days) * 100 |

## 2) TO-BE (как улучшить)

| Дифинишн | Калькулейшнс | Юнитс | Энтитис | Грейнс | Коммитментсы | Контекст JSON | Что означает | Какие ивенты используются для расчета | Как считается |
|---|---|---|---|---|---|---|---|---|---|
| velocity | velocity_planned_sp, velocity_completed_sp, velocity_planned_count, velocity_completed_count | story_points, issues | sprint (entity_id=sprint_id) | sprint | Сохранять sprint_start_at/sprint_end_at в фактах | Минимальный, как и сейчас | План vs факт по спринту в SP и в количестве задач | Sprint start/end, membership issue в спринте, статус на конец спринта | Текущая формула velocity, без velocity_predictability_pct |
| cycle_time | customer_lead_time, ttm_days | days | issue (customer_lead_time), epic (ttm_days) | issue | Используются commitment_rules (start/end); для ttm_days настройки через settings_id -> calculation_settings (JSONB) | Ограниченный | Метрики времени потока: customer lead time + TTM (перенесен из ttm) | Для customer_lead_time: переход issue в start/end column; для ttm_days: только Epic, commitment_start -> commitment_end | customer_lead_time = event_end_at - event_start_at; ttm_days считается только для Epic по настройкам |
| throughput | throughput_count | issues | project/week bucket | week | Использовать commitment_rules, конкретно end_column как точку завершения | Ограниченный | Количество завершенных задач за неделю | Событие попадания задачи в end_column | Count задач, достигших end_column в пределах ISO-week |
| cfd | cfd_count | issues | board_column/status | day | Нет | Ограниченный | Снимок количества задач по колонкам статуса на день | Состояние issue в колонке на дату среза | Daily snapshot count по status/column |
| backlog_growth | backlog_size, backlog_added, backlog_removed | issues | project | day | Не требуется | Ограниченный | Размер и движение бэклога | Created, unresolved state, изменения sprint membership | Для Scrum: backlog_size = все незавершенные задачи вне активного спринта; backlog_added = все, кто добавлен в backlog за день (включая выведенные из спринта); backlog_removed = все, кто покинул backlog |
| aging | age_in_status | days | issue + status | issue/status | Не зависит от commitment points | Ограниченный | Сколько дней задача провела в каждом статусе | Все события входа/выхода задачи в/из статуса | Суммировать все интервалы пребывания в каждом статусе по задаче, включая повторные заходы |
| flow_efficiency | flow_active_days, flow_wait_days, flow_efficiency_pct | days, percent | issue | issue | Используются; для каждого проекта обязательна разметка активных и неактивных колонок | Ограниченный | Доля активного времени в общем времени потока | Переходы по статусам, разделение active vs wait | flow_efficiency_pct = flow_active_days / (flow_active_days + flow_wait_days) * 100 |

## Назначение документа

1. Зафиксировать, какие метрики и расчеты уже есть в системе сейчас.
2. Зафиксировать целевое улучшение структуры метрик, контекста и событий расчета для следующей итерации.
