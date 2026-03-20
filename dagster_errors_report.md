# Отчет об ошибках выполнения джобов Dagster (19.03.2026)

В ходе последовательного перезапуска всех джобов в системе были выявлены критические ошибки в логике ассетов и проверках качества данных. Ниже приведен детальный список.

## 1. Системная ошибка в механизме слайсинга (TypeError)

**Описание:** Вызов функции `apply_slicing` падает из-за отсутствия обязательного аргумента `engine`. Это блокирует расчет нарезанных (sliced) метрик для большинства показателей.

*   **Локации:**
    *   `pipelines/assets/metrics/lead_time.py`, строка 258 (в `calculate_lead_time`)
    *   `pipelines/assets/metrics/throughput.py`, строка 153 (в `calculate_throughput`)
    *   `pipelines/assets/metrics/backlog_growth.py`, строка 244 (в `calculate_backlog_growth`)
*   **Причина:** Функция `apply_slicing` в `pipelines/utils/smart_slicer.py` (или `slicing_utils.py`) ожидает `engine` для выполнения SQL-запросов, но в указанных ассетах он не передается при вызове.

---

## 2. Ошибки синтаксиса SQL в проверках качества (Asset Checks)

**Описание:** Проверки данных (`Asset Checks`) падают с ошибкой `ProgrammingError` при попытке выполнить проверочный SQL-запрос.

*   **Локации:**
    *   `pipelines/assets/metrics/velocity.py`, строка 465 (в `velocity_data_quality_check`)
    *   `pipelines/assets/metrics/cumulative_flow.py`, строка 154 (в `cfd_data_quality_check`)
    *   `pipelines/assets/metrics/advanced.py`, строка 232 (в `advanced_metrics_data_quality_check`)
*   **Текст ошибки:** `sqlalchemy.exc.ProgrammingError: (psycopg2.errors.SyntaxError) syntax error at or near ":"`
*   **Причина:** Использование синтаксиса именованных параметров `:calc_id` в строке запроса. Используемый метод `read_table` (через `exec_driver_sql` в SQLAlchemy/Pandas) ожидает либо сырой SQL без таких меток, либо другой формат связывания параметров для используемого драйвера.

---

## 3. Ошибка несовместимости типов в расчете TTM (PanicException)

**Описание:** Расчет Time to Market падает на уровне движка Polars при выполнении арифметической операции.

*   **Локация:** `pipelines/calculations/time_to_market.py`, строка 108 (вызывается из `pipelines/assets/metrics/time_to_market.py`, строка 92)
*   **Текст ошибки:** `pyo3_runtime.PanicException: data types don't match: InvalidOperation(ErrString("sub operation not supported for dtypes str and str"))`
*   **Причина:** Попытка вычесть одну колонку из другой (`commitment_end_at - commitment_start_at`), когда обе колонки имеют тип `String`, а не `Datetime`. Данные из Jira загрузились как строки и не были приведены к временному формату перед расчетом.

---

## Итог по джобам

| Джоб | Результат | Комментарий |
| :--- | :--- | :--- |
| `jira_raw_job` | ✅ Успех | Данные загружены. |
| `jira_clean_job` | ✅ Успех | Схема `clean_jira` обновлена. |
| `recalculate_velocity_job` | ❌ Ошибка | Расчет прошел, но упал Asset Check (SQL Syntax). |
| `recalculate_lead_time_job` | ❌ Ошибка | Упал основной расчет (TypeError в slicing). |
| `recalculate_throughput_job` | ❌ Ошибка | Упал основной расчет (TypeError в slicing). |
| `recalculate_cfd_job` | ❌ Ошибка | Расчет прошел, но упал Asset Check (SQL Syntax). |
| `recalculate_backlog_growth_job` | ❌ Ошибка | Упал основной расчет (TypeError в slicing). |
| `recalculate_time_to_market_job` | ❌ Ошибка | Упал основной расчет (Типы данных в Polars). |
