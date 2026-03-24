# Спецификация дашборда Metabase: Sprint Performance & Stability

Этот дашборд предназначен для глубокого анализа качества планирования, динамики выполнения и предсказуемости команды на основе данных из `metrics.v_facts`.

---

## 1. Глобальные фильтры (Dashboard Filters)
Располагаются в верхней части дашборда и применяются ко всем виджетам:

1.  **Project Key:** Слайсер по коду проекта (`dp.project_key`). *Обязательный.*
2.  **Sprint Name/ID:** Выбор конкретного спринта (`fv.entity_id`).
    *   *Важно:* Для исторических графиков (Velocity) этот фильтр должен быть настроен на "Last 5-10 Sprints" или не ограничивать выборку до одного значения.
3.  **Date Range:** Период дат (`dt.full_date`). Позволяет фильтровать спринты по времени.
4.  **Issue Type (Slice):** Фильтр по типам задач (`fv.slice_value`).
    *   *Условие в SQL:* `AND slice_rule_name = 'By Issue Type' AND slice_value = {{issue_type}}`.

---

## 2. Структура дашборда

### Ряд 1: Текущий спринт (Оперативный контроль)
*Фокус на ходе выполнения текущего выбранного спринта.*

#### 1.1. График: Sprint Burndown (Сгорание работ)
*   **Тип визуализации:** Line Chart.
*   **Ось X:** `full_date` (Дата дня спринта).
*   **Ось Y:** `value` (Story Points).
*   **Данные:** `calc_code = 'sprint_burndown_remaining_sp'`.
*   **Группировка:** По дате (`full_date`).
*   **Настройка:** В Metabase добавить "Идеальную линию" (линейный спуск от начального объема до 0 к дате окончания).

#### 1.2. График: Activation Velocity (Динамика запуска)
*   **Тип визуализации:** Area Chart.
*   **Ось X:** `full_date` (Дата).
*   **Ось Y:** `value` (Проценты % от 0 до 100).
*   **Данные:** `calc_code = 'activation_velocity_pct'`.
*   **Группировка:** По дате.
*   **Суть:** Показывает, какой % обязательств команда уже перевела из To Do в работу.

---

### Ряд 2: Стабильность плана (Added vs Removed)
*Анализ "дырявости" границ спринта и изменений на лету.*

#### 2.1. График: Scope Stability (Приток и отток задач)
*   **Тип визуализации:** Grouped Bar Chart (Столбики в разные стороны).
*   **Ось X:** `iteration_name` (Имя спринта) или `entity_id`.
*   **Ось Y:** `SUM(value)` (Story Points).
*   **Данные и Группировка:**
    *   Серия 1 (Added): `calc_code = 'sprint_added_sp_sum'` (Столбик вверх).
    *   Серия 2 (Removed): `calc_code = 'sprint_removed_sp_sum'` (Значение `value * -1`, столбик вниз).
*   **Суть:** Если столбики высокие в обе стороны — планирование было некачественным.

#### 2.2. Карточка: Scope Churn Rate (%)
*   **Тип визуализации:** Number (KPI Card).
*   **Данные:** Расчетное значение `(SUM(added_sp) + SUM(removed_sp)) / Planned_SP * 100`.
*   **Суть:** Коэффициент нестабильности плана.

---

### Ряд 3: Velocity и Предсказуемость (Тренды)
*Исторический обзор эффективности за последние 5–10 спринтов.*

#### 3.1. График: Velocity Say/Do (План vs Факт)
*   **Тип визуализации:** Combo Chart (Bar + Line).
*   **Ось X:** `full_date` (Дата старта спринта) или `iteration_name`.
*   **Ось Y (Левая):** `value` (Story Points).
*   **Ось Y (Правая):** `%` (Проценты).
*   **Серии:**
    1.  **Planned:** `calc_code = 'velocity_planned_sp'` (Столбик).
    2.  **Completed:** `calc_code = 'velocity_completed_sp'` (Столбик).
    3.  **Predictability %:** Линия поверх столбиков (Расчет: `completed / planned * 100`).
*   **Суть:** Главный график емкости команды.

#### 3.2. График: Velocity in Issues (В штуках)
*   **Тип визуализации:** Bar Chart.
*   **Данные:** `velocity_planned_count` и `velocity_completed_count`.
*   **Суть:** Сравнение плана и факта в количестве тикетов.

---

### Ряд 4: Хвосты и Качество данных
*Анализ незавершенки и корректности процесса.*

#### 4.1. График: Spillover Count (Задачи-хвосты)
*   **Тип визуализации:** Bar Chart.
*   **Ось X:** `iteration_name`.
*   **Ось Y:** `value` (Количество задач).
*   **Данные:** `calc_code = 'sprint_spillover_count'`.
*   **Суть:** Показывает, сколько задач систематически переходит в следующий спринт.

#### 4.2. График: Unestimated Closed Rate (Задачи без оценки)
*   **Тип визуализации:** Bar Chart.
*   **Данные:** `unestimated_closed_count`.
*   **Группировка:** По Спринту.
*   **Суть:** Доля закрытых задач без Story Points. Если показатель > 20%, Velocity недостоверен.

---

## 3. Техническая справка по SQL (v_facts)

| Метрика | calc_code | entity_type | Смысл value |
| :--- | :--- | :--- | :--- |
| **Burndown** | `sprint_burndown_remaining_sp` | `sprint` | Остаток SP на день |
| **Activation** | `activation_velocity_pct` | `sprint` | % в работе |
| **Added SP** | `sprint_added_sp_sum` | `sprint` | Сумма добавленных SP |
| **Removed SP** | `sprint_removed_sp_sum` | `sprint` | Сумма удаленных SP |
| **Planned SP** | `velocity_planned_sp` | `sprint` | Коммитмент |
| **Completed SP** | `velocity_completed_sp` | `sprint` | Факт закрытия |
| **Spillover** | `sprint_spillover_count` | `sprint` | Кол-во хвостов |
| **Unestimated** | `unestimated_closed_count` | `sprint` | Кол-во задач без SP |
