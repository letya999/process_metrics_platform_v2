# Velocity Anomaly Investigation (TWAD, ADS Sprints 24-28)

## 1. Что было целью

Понять, почему значения velocity (Plan/Fact) и состав задач по спринтам в `sprints_velocity.md` не совпадают с данными в нашей БД (`clean_jira`, `metrics`), и локализовать источник расхождений.

---

## 2. Откуда брал данные

### 2.1 Локальные источники в проекте

- Эталонный файл пользователя:
  - `sprints_velocity.md`
- Данные БД:
  - `metrics.v_facts` (velocity calc codes)
  - `metrics.fact_velocity`
  - `clean_jira.sprints`
  - `clean_jira.sprint_issues`
  - `clean_jira.sprint_issues_changelog`
  - `clean_jira.issue_status_changelog`
  - `clean_jira.issues`
  - `clean_jira.issue_statuses`
  - `raw_jira.issues`
  - `raw_jira.issues__fields__customfield_10020`
  - `raw_jira.issues__changelog__histories`
  - `raw_jira.issues__changelog__histories__items`
  - `raw_jira._dlt_loads`

### 2.2 Jira API (онлайн проверка)

- Jira credentials: взяты из `.env` (`JIRA_BASE_URL`, `JIRA_USER_EMAIL`, `JIRA_API_TOKEN`) по явному разрешению пользователя.
- Эндпоинты:
  - `/rest/agile/1.0/board?projectKeyOrId=TWAD` -> board id = `83` (`Доска ADS`)
  - `/rest/greenhopper/1.0/rapid/charts/sprintreport?rapidViewId=83&sprintId=...`
  - точечная проверка issue existence:
    - `/rest/api/3/issue/TWAD-482`
    - `/rest/api/3/issue/TWAD-484`
    - `/rest/api/3/issue/TWAD-487`

---

## 3. Что именно сравнивал

1. Sprint-level Plan/Fact:
- `sprints_velocity.md` vs `metrics.v_facts` (TWAD, velocity, no slice)

2. Issue-level по ADS 24-28:
- Категории Jira sprint report:
  - `completedIssues`
  - `issuesNotCompletedInCurrentSprint`
  - `puntedIssues`
  - `issuesCompletedInAnotherSprint`
- Сопоставление категорий Jira с:
  - `clean_jira.issues` (issue присутствует в модели)
  - `clean_jira.sprint_issues` (issue связан со sprint)
  - `clean_jira.sprint_issues_changelog` (есть история add/remove в sprint)

3. Проверка цепочки raw -> clean:
- Есть ли “проблемные” ключи в `raw_jira.issues`
- Есть ли по ним sprint/changelog события в raw-таблицах
- Время последней загрузки (`raw_jira._dlt_loads`) для важных таблиц

---

## 4. Как исследовал аномалии (подход)

1. Сначала собрал базовую сверку спринтов и дельты по Plan/Fact.
2. Затем зафиксировал “истину” из Jira Sprint Report (прямой API, board 83) и сохранил локально:
   - `scripts/jira_ads_24_28_sprintreport.json`
3. Сверил Jira-ключи по каждому спринту с clean-слоем (issues/sprint_issues/changelog).
4. Для задач, вызывающих вопросы, посмотрел raw sprint/changelog записи:
   - `raw_jira.issues__fields__customfield_10020`
   - `raw_jira.issues__changelog__histories*`
5. Проверил “живое” существование задач в Jira API для ключей, которых нет в БД.

---

## 5. Что обнаружено

## 5.1 Спринтовые расхождения Plan/Fact остаются существенными

После нескольких итераций правок алгоритма velocity (done mapping, completed-only sprints, stricter fallback) расхождения уменьшились частично, но не исчезли. Наибольший выброс остался в ADS Sprint 28.

## 5.2 По issue-level есть реальные пробелы данных в clean-слое

Критичные примеры:

- ADS Sprint 25:
  - В `clean_jira.sprint_issues_changelog` отсутствуют `TWAD-436`, `TWAD-438` (при том, что в Jira sprint report они есть).
- ADS Sprint 26:
  - В `clean_jira.sprint_issues_changelog` отсутствуют `TWAD-449`, `TWAD-460`.
- ADS Sprint 27:
  - `TWAD-474` отсутствует в `clean_jira.sprint_issues` и `clean_jira.sprint_issues_changelog`.
- ADS Sprint 28:
  - В `clean_jira.issues` отсутствуют `TWAD-482`, `TWAD-484`, `TWAD-487`.
  - Из-за этого они не могут участвовать ни в sprint membership, ни в completed/punted логике.

## 5.3 Некоторые “пропавшие” ключи в Jira существуют и доступны

Проверка `/rest/api/3/issue/{key}`:
- `TWAD-482` -> 200
- `TWAD-484` -> 200
- `TWAD-487` -> 200

То есть задача не “удалена в Jira”; она есть, но отсутствует в нашем raw/clean контурах.

## 5.4 Признак устаревания raw issues

По `raw_jira.issues` максимальный `_dlt_load_id` указывает на загрузку от **2026-02-19**.
При этом спорные задачи и изменения по Sprint 28 происходили позже (конец февраля/март), что объясняет неполноту.

---

## 6. Изменения в коде, которые были сделаны в этой ветке

1. Velocity:
- done status resolution ориентирован на board mapping/right-most column с fallback.
- добавлена поддержка явного `done_status_ids` в `calculate_velocity_facts`.
- добавлен strict режим `allow_current_status_fallback=False` для completed вычисления в asset.

2. Asset-level:
- velocity считается только по закрытым спринтам (`complete_date IS NOT NULL`).
- `sprint_issues` fallback ограничен `is_active=true`.
- done statuses для velocity берутся из `metrics.commitment_rules` (с fallback на `lead_time_days` rules).

3. Диагностика/скрипты:
- `scripts/compare_sprints_velocity_with_db.py`
- `scripts/reconcile_ads_24_28_issue_level.py`
- `scripts/jira_ads_24_28_sprintreport.json` (снимок Jira sprint report 24-28)

---

## 7. Моя рабочая гипотеза причин

Главная причина расхождений сейчас: **не только формула velocity**, а прежде всего **неполный/устаревший raw/clean слой по issue и sprint history**.

То есть pipeline расчета уже достаточно близок по семантике, но входные данные не полностью соответствуют текущему состоянию Jira Sprint Report.

---

## 8. Что нужно делать дальше (практично)

1. Починить/перезапустить ingestion raw issues и changelog в полном объеме (TWAD), убедиться что `TWAD-482/484/487` попадают в `raw_jira.issues` и далее в `clean_jira.issues`.
2. Проверить, почему часть sprint changelog событий не попадает в `clean_jira.sprint_issues_changelog` (кейсы 436/438/449/460/474).
3. После обновления данных:
   - пересчитать `calculate_velocity`,
   - заново прогнать sprint-level и issue-level reconciliation.
4. Зафиксировать issue-level golden tests для ADS 24-28 как обязательный regression gate.

---

## 9. Важные артефакты для продолжения в новом чате

- [sprints_velocity.md](C:\Users\User\a_projects\process_metrics_platform_v2\sprints_velocity.md)
- [scripts/jira_ads_24_28_sprintreport.json](C:\Users\User\a_projects\process_metrics_platform_v2\scripts\jira_ads_24_28_sprintreport.json)
- [scripts/compare_sprints_velocity_with_db.py](C:\Users\User\a_projects\process_metrics_platform_v2\scripts\compare_sprints_velocity_with_db.py)
- [scripts/reconcile_ads_24_28_issue_level.py](C:\Users\User\a_projects\process_metrics_platform_v2\scripts\reconcile_ads_24_28_issue_level.py)
- [pipelines/assets/metrics/velocity.py](C:\Users\User\a_projects\process_metrics_platform_v2\pipelines\assets\metrics\velocity.py)
- [pipelines/calculations/velocity.py](C:\Users\User\a_projects\process_metrics_platform_v2\pipelines\calculations\velocity.py)

---

## 10. Runbook проверки после реинжеста

Ниже чек-лист, который можно выполнять последовательно после перезагрузки raw/clean слоя.

1. Проверить свежесть raw-таблиц:
- `raw_jira._dlt_loads` по таблицам `issues`, `issues__fields__customfield_10020`, `issues__changelog__histories`, `issues__changelog__histories__items`.
- Ожидание: `inserted_at` не старее даты последнего закрытия ADS Sprint 28 (и точно позже **2026-02-19**).

2. Проверить, что “пропавшие” ключи есть в raw:
- `TWAD-482`, `TWAD-484`, `TWAD-487` должны быть в `raw_jira.issues`.
- Для них должны быть строки sprint field в `raw_jira.issues__fields__customfield_10020`.

3. Проверить, что ключи дошли в clean:
- `clean_jira.issues`: наличие `TWAD-482/484/487`.
- `clean_jira.sprint_issues` и `clean_jira.sprint_issues_changelog`: наличие membership/history для кейсов `436/438/449/460/474/482/484/487`.

4. Пересчитать метрики velocity:
- Перезапустить materialization для `calculate_velocity`.
- Зафиксировать обновленный срез `metrics.v_facts` (TWAD, metric = velocity, no slice).

5. Повторить reconciliation:
- Sprint-level: `scripts/compare_sprints_velocity_with_db.py`.
- Issue-level: `scripts/reconcile_ads_24_28_issue_level.py`.
- Сохранить результат в отдельный артефакт (json/csv), чтобы сравнить “до/после”.

---

## 11. Критерии закрытия инцидента

Инцидент можно считать закрытым только если одновременно выполняются условия:

1. По ADS Sprint 24-28 нет отсутствующих issue в `clean_jira.issues`, которые при этом отдаются Jira API.
2. Для всех проблемных ключей есть корректный sprint membership/changelog в clean-слое.
3. Расхождение Plan/Fact между `sprints_velocity.md` и `metrics.v_facts` укладывается в согласованный допуск:
- либо `0` (полное совпадение),
- либо явно задокументированный бизнес-допуск, согласованный с владельцем метрики.
4. Regression gate проходит стабильно:
- issue-level golden test для ADS 24-28 включен в CI,
- тесты не флапают минимум на 2 последовательных прогонах.

---

## 12. Риски, если оставить как есть

1. Sprint 28 и следующие спринты будут занижать факт velocity из-за неполного issue coverage.
2. Любые улучшения формулы velocity не дадут ожидаемого эффекта, пока входные Jira-данные неполные.
3. Аналитика спринтов (commitment reliability, carry-over, punted behavior) останется недостоверной для управленческих выводов.

---

## 13. Продолжение расследования (2026-03-19)

### 13.1 Что дополнительно подтвердили

1. `raw_jira._dlt_loads` показывал свежие загрузки от **2026-03-19**, но по факту в `raw_jira.issues` для TWAD верхняя `fields__updated` оставалась на **2026-02-19**.
2. Jira API в реальном времени отдавал проблемные ключи:
   - `TWAD-482` (updated: 2026-03-18),
   - `TWAD-484` (updated: 2026-02-26),
   - `TWAD-487` (updated: 2026-03-19).
3. До фикса в `raw_jira.issues` отсутствовали `TWAD-482/484/487`.

### 13.2 Что исправлено в коде

1. `pipelines/assets/jira/raw.py`:
   - в incremental-запрос `issues` добавлен защитный lookback (`JIRA_ISSUES_LOOKBACK_DAYS`, default = 45 дней),
   - добавлен детерминированный порядок `ORDER BY updated ASC, key ASC`.
   Это снижает риск пропусков из-за дрейфа incremental state и пограничных обновлений.

2. `pipelines/assets/jira/clean.py`:
   - в `clean_jira_sprint_issues` и `clean_jira_sprint_issues_changelog` расширен фильтр sprint-событий:
     - было: `item.field = 'Sprint'`
     - стало: `item.field = 'Sprint' OR item.field_id = 'customfield_10020'`
   Это покрывает случаи, где поле спринта приходит через `field_id`.

### 13.3 Что выполнено после фикса

1. Выполнен реинжест raw по TWAD с lookback 90 дней (`pipeline_name = jira_raw_TWAD`).
2. Пересобраны clean-ассеты Jira:
   - projects, issue_types, issue_statuses, issues, sprints,
   - issue_status_changelog, sprint_issues, sprint_issues_changelog.
3. Пересчитан `calculate_velocity`.

### 13.4 Проверка результата (после пересчета)

1. Проблемные ключи теперь присутствуют в clean-слое:
   - `TWAD-482/484/487` есть в `clean_jira.issues`,
   - есть их записи в `clean_jira.sprint_issues` и `clean_jira.sprint_issues_changelog`.

2. Sprint 28 заметно улучшился относительно состояния до фикса:
   - было: `db_plan = 5`, `db_fact = 0`
   - стало: `db_plan = 27`, `db_fact = 6`
   - эталон (`sprints_velocity.md`): `plan = 36`, `fact = 7`

3. Итог: критичный провал Sprint 28 устранен частично (данные перестали быть пустыми), но полное совпадение с эталоном еще не достигнуто.

### 13.5 Остаточные гипотезы (что проверять дальше)

1. Семантический разрыв между Jira Sprint Report и текущей логикой `commitment/completed` (особенно по added-after-start и removed).
2. Возможные отличия в board-scoped done-статусах на момент закрытия спринта.
3. Часть historical sprint membership может требовать дополнительной нормализации по моменту времени, а не только по последнему действию.

---

## 14. Дополнительные действия (после 13.5)

1. Скорректирована логика расчета `completed` в velocity:
   - теперь completed трактуется как завершение **внутри окна спринта** (`start_date < completion <= end/complete_date`), а не просто “done к концу спринта”.
   - это выровняло один из системных перекосов по факту (например, для ADS 22 факт в `metrics.v_facts` стал совпадать с `sprints_velocity.md`).

2. Добавлен regression-check для инцидентных ключей ADS 24-28:
   - новый тест `tests/validation/test_velocity_incident_regression.py` проверяет, что ключи `436/438/449/460/474/482/484/487` присутствуют в:
     - `clean_jira.issues`,
     - `clean_jira.sprint_issues`,
     - `clean_jira.sprint_issues_changelog`.

3. Улучшен диагностический скрипт issue-level reconciliation:
   - `scripts/reconcile_ads_24_28_issue_level.py` теперь берет expected из JSON-артефакта (`jira_ads_24_28_sprintreport_current.json` или fallback-файла), а не из жестко вшитых множествах в коде.

### Текущее состояние после полного прогона

1. Пропавшие ключи по Sprint 28 восстановлены в raw/clean.
2. Критический провал Sprint 28 устранен частично:
   - факт перестал быть нулевым (`db_fact` больше не `0`),
   - но сохраняется разница с эталоном (`db_plan/db_fact` vs `sprints_velocity.md`), что указывает уже на остаточный семантический разрыв, а не на чистую потерю данных.

### Актуальная сверка с эталоном (после последних правок plan/fact)

- По `Fact` (Completed, SP): полное совпадение со `sprints_velocity.md` для ADS 17-28.
- По `Plan` (Commitment, SP): остались расхождения, в том числе:
  - ADS 25: `db_plan=23` vs `md_plan=30` (delta `-7`)
  - ADS 28: `db_plan=38` vs `md_plan=36` (delta `+2`)

Вывод: проблема “факт = 0” закрыта, формула completed приведена к эталону; remaining gap сосредоточен в определении состава Plan.

---

## 15. Полный журнал проделанной работы (что делал, куда копал, что смотрел)

### 15.1 Что уже сделано по коду

1. Raw ingestion (`pipelines/assets/jira/raw.py`):
   - добавлен защитный lookback для incremental выгрузки issues:
     - env: `JIRA_ISSUES_LOOKBACK_DAYS` (default `45`),
   - в JQL добавлен детерминированный порядок:
     - `ORDER BY updated ASC, key ASC`.

2. Clean layer (`pipelines/assets/jira/clean.py`):
   - в `clean_jira_sprint_issues` и `clean_jira_sprint_issues_changelog` расширен фильтр sprint-изменений:
     - `item.field = 'Sprint' OR item.field_id = 'customfield_10020'`.
   - в snapshot fallback (`clean_jira_sprint_issues`) добавлено ограничение:
     - не добавлять snapshot-события, если у issue уже есть sprint changelog.

3. Velocity calculation (`pipelines/calculations/velocity.py`):
   - `Fact` (completed) переопределен как completion **внутри окна спринта**:
     - `start_date < completion <= complete_date/end_date`,
   - `Plan` временно переключался и сравнивался в нескольких вариантах:
     - commitment по стартовому срезу,
     - final scope c SP на старте,
     - as-of close фильтрация по changelog,
   - выбран наиболее близкий к эталону вариант (на текущем этапе лучше всего совпадает по ADS 24/27/28).

4. Диагностика и guardrails:
   - добавлен regression test:
     - `tests/validation/test_velocity_incident_regression.py`
   - reconciliation script переведен на expected из JSON-артефакта:
     - `scripts/reconcile_ads_24_28_issue_level.py`
   - сохранен актуальный снимок sprint report:
     - `scripts/jira_ads_24_28_sprintreport_current.json`.

### 15.2 Что запускал/пересчитывал

1. Реинжест raw по TWAD с lookback (после фикса ingestion).
2. Пересборка clean-активов Jira:
   - `clean_jira_projects`,
   - `clean_jira_issue_types`,
   - `clean_jira_issue_statuses`,
   - `clean_jira_issues`,
   - `clean_jira_sprints`,
   - `clean_jira_issue_status_changelog`,
   - `clean_jira_sprint_issues`,
   - `clean_jira_sprint_issues_changelog`.
3. Пересчет метрики:
   - `calculate_velocity`.
4. Повторные сверки:
   - `python scripts/compare_sprints_velocity_with_db.py`,
   - `python scripts/reconcile_ads_24_28_issue_level.py`.

### 15.3 Что проверял в БД/данных (куда копал)

1. Свежесть raw и dlt-state:
   - `raw_jira._dlt_loads`,
   - `raw_jira._dlt_pipeline_state`.
2. Наличие инцидентных ключей:
   - `raw_jira.issues`,
   - `clean_jira.issues`,
   - `clean_jira.sprint_issues`,
   - `clean_jira.sprint_issues_changelog`.
3. Источники sprint membership:
   - `raw_jira.issues__fields__customfield_10020`,
   - `raw_jira.issues__changelog__histories`,
   - `raw_jira.issues__changelog__histories__items`.
4. Слой метрик:
   - `metrics.v_facts` (calc codes: planned/completed SP & count).

### 15.4 Что дергал во внешнем Jira API

Использовались read-only проверки:

1. Board discovery:
   - `GET /rest/agile/1.0/board?projectKeyOrId=TWAD` (board `83`).
2. Sprint report truth source:
   - `GET /rest/greenhopper/1.0/rapid/charts/sprintreport?rapidViewId=83&sprintId={id}`.
3. Проверка существования issues:
   - `GET /rest/api/3/issue/TWAD-482`
   - `GET /rest/api/3/issue/TWAD-484`
   - `GET /rest/api/3/issue/TWAD-487`
4. Проверка выборки JQL:
   - `GET /rest/api/3/search/jql` с фильтром `project in (TWAD) AND updated >= ...`.

### 15.5 Какие артефакты и файлы смотрел

- [velocity_anomaly_investigation.md](C:\Users\User\a_projects\process_metrics_platform_v2\velocity_anomaly_investigation.md)
- [sprints_velocity.md](C:\Users\User\a_projects\process_metrics_platform_v2\sprints_velocity.md)
- [scripts/jira_ads_24_28_sprintreport.json](C:\Users\User\a_projects\process_metrics_platform_v2\scripts\jira_ads_24_28_sprintreport.json)
- [scripts/jira_ads_24_28_sprintreport_current.json](C:\Users\User\a_projects\process_metrics_platform_v2\scripts\jira_ads_24_28_sprintreport_current.json)
- [scripts/compare_sprints_velocity_with_db.py](C:\Users\User\a_projects\process_metrics_platform_v2\scripts\compare_sprints_velocity_with_db.py)
- [scripts/reconcile_ads_24_28_issue_level.py](C:\Users\User\a_projects\process_metrics_platform_v2\scripts\reconcile_ads_24_28_issue_level.py)
- [pipelines/assets/jira/raw.py](C:\Users\User\a_projects\process_metrics_platform_v2\pipelines\assets\jira\raw.py)
- [pipelines/assets/jira/clean.py](C:\Users\User\a_projects\process_metrics_platform_v2\pipelines\assets\jira\clean.py)
- [pipelines/calculations/velocity.py](C:\Users\User\a_projects\process_metrics_platform_v2\pipelines\calculations\velocity.py)
- [pipelines/assets/metrics/velocity.py](C:\Users\User\a_projects\process_metrics_platform_v2\pipelines\assets\metrics\velocity.py)
- [tests/validation/test_velocity_incident_regression.py](C:\Users\User\a_projects\process_metrics_platform_v2\tests\validation\test_velocity_incident_regression.py)

### 15.6 Текущие рабочие гипотезы по remaining gap (Plan)

1. Оставшееся расхождение почти полностью в `Plan`, а не в `Fact`.
2. Вероятный корень: различие бизнес-семантики commitment между:
   - Jira Sprint Report,
   - текущей моделью `final_scope/start_scope + historical SP at start`.
3. Возможные конкретные причины:
   - пост-фактум правки sprint membership после закрытия,
   - разница в трактовке removed/re-added в пределах одного спринта,
   - различие в том, какие issue считаются “учтенными в Plan” при scope-change,
   - нюансы по zero/empty SP на момент старта (когда SP присваивается позже).
