# ROADMAP - Process Metrics Platform v2

План задач для перехода на новую архитектуру и создания MVP.

---

## Phase 0: Подготовка инфраструктуры ✅

### 0.1 Настройка проекта
- [x] Обновить `pyproject.toml` под новый стек (Dagster вместо Prefect)
- [x] Создать новый `requirements.txt`
- [x] Обновить `docker-compose.yml` (4 контейнера: postgres, app, dagster, metabase)
- [x] Создать `Dockerfile` для app
- [x] Создать `Dockerfile.dagster` для Dagster
- [x] Создать `.env.example` с примерами переменных

### 0.2 Makefile
- [x] Создать `Makefile` с командами:
  - `make check` — lint + test + validate
  - `make dev` — docker-compose up
  - `make test` — pytest с coverage
  - `make lint` — ruff + black check
  - `make format` — auto-fix
  - `make validate` — проверка данных
  - `make migrate` — Alembic migrations

### 0.3 Структура директорий
- [x] Создать структуру `app/` (FastAPI)
- [x] Создать структуру `pipelines/` (Dagster)
- [x] Создать структуру `db/` (schemas, views, migrations)
- [x] Создать структуру `tests/` (unit, integration, validation)

---

## Phase 1: База данных ✅

### 1.1 Упрощённые схемы
- [x] Создать `db/init/01_create_schemas.sql` — создание схем
- [x] Создать `db/schemas/platform.sql` — упрощённая platform схема (~100 строк)
  - users, integrations, metric_configs
- [x] Создать `db/schemas/clean_jira.sql` — упрощённая clean схема (~150 строк)
  - issues, status_changes, sprints
- [x] Создать `db/views/metrics.sql` — materialized views (~100 строк)
  - mv_lead_time, mv_velocity, mv_throughput

### 1.2 Alembic
- [x] Инициализировать Alembic в `db/migrations/`
- [x] Создать начальную миграцию для platform схемы
- [ ] Тесты миграций (up + down)

---

## Phase 2: Dagster Pipeline (Jira) ✅

### 2.1 Raw слой (dlt)
- [x] Создать `pipelines/assets/jira/raw.py`
  - dlt source для Jira Cloud
  - Загрузка issues, sprints, changelogs
  - Incremental loading (append-only)
- [x] Тесты для raw asset

### 2.2 Clean слой
- [x] Создать `pipelines/assets/jira/clean.py`
  - Asset: `clean_jira_issues`
  - Asset: `clean_jira_sprints`
  - Asset: `clean_jira_status_changes`
  - Трансформация raw → clean
- [x] Data validation checks (asset_check)
- [x] Тесты для clean assets

### 2.3 Metrics слой
- [x] Создать `pipelines/assets/metrics/refresh.py`
  - Asset: `metrics_lead_time`
  - Asset: `metrics_velocity`
  - Asset: `metrics_throughput`
  - Refresh materialized views
- [x] Тесты для metrics assets

### 2.4 Dagster Configuration
- [x] Создать `pipelines/definitions.py` — Definitions entry point
- [x] Создать `pipelines/resources/database.py` — DB resource
- [x] Создать `pipelines/jobs/schedules.py` — Cron schedules
- [ ] Проверить assets в Dagster UI

---

## Phase 3: FastAPI Admin API ✅

### 3.1 Модели
- [x] Создать `app/models/orm.py`
  - User, Integration, MetricConfig
- [x] Pydantic schemas для API

### 3.2 API Endpoints
- [x] Создать `app/api/integrations.py`
  - CRUD для интеграций (Jira, GitLab, etc.)
  - POST /api/v1/integrations/{id}/sync — триггер синхронизации
- [x] Создать `app/api/projects.py`
  - Выбор проектов для синхронизации
- [x] Создать `app/api/metrics.py`
  - Конфигурация метрик (commitment points, estimation fields)

### 3.3 Services
- [x] Создать `app/services/dagster_client.py`
  - Триггер Dagster jobs через GraphQL API
- [x] Тесты для API

### 3.4 Main App
- [x] Создать `app/main.py`
  - FastAPI app
  - Lifespan (startup/shutdown)
  - CORS, middleware

---

## Phase 4: Тестирование и валидация ✅

### 4.1 Unit Tests
- [x] Тесты для Jira client (parsing)
- [x] Тесты для трансформаций (raw → clean)
- [x] Тесты для расчёта метрик (lead time, velocity)

### 4.2 Integration Tests
- [x] Тесты API endpoints
- [x] Тесты Dagster assets (с тестовой БД)

### 4.3 Data Validation
- [x] Создать `tests/validation/test_data_integrity.py`
- [x] Валидация FK relationships
- [x] Валидация NULL constraints
- [x] Валидация materialized views

### 4.4 Coverage
- [ ] Достичь >= 75% overall coverage
- [ ] >= 80% для services/ и assets/

---

## Phase 5: Docker & Deployment ✅

### 5.1 Docker Setup
- [x] Финализировать `docker-compose.yml`
- [x] Проверить все 4 контейнера работают
- [x] Health checks для всех сервисов

### 5.2 Metabase
- [ ] Настроить подключение к metrics схеме
- [ ] Создать базовые дашборды:
  - Lead Time distribution
  - Velocity trend
  - Throughput chart

### 5.3 Documentation
- [ ] Обновить README.md
- [ ] Quick Start Guide
- [ ] Screenshots

---

## Phase 6: Cleanup (удаление старого кода) ✅

### 6.1 Удалить микросервисы
- [x] Удалить `services/dlt_jira_loader/` (не существует)
- [x] Удалить `services/orchestrator/` (не существует)
- [x] Удалить `services/cleaner/` (не существует)
- [x] Удалить `services/metrics/` (не существует)
- [x] Удалить `services/admin/` (не существует)

### 6.2 Удалить старые конфиги
- [x] Удалить Prefect-related файлы (не существует)
- [x] Удалить dbt-related файлы (не существует)
- [x] Удалить Redis-related конфигурации (не существует)
- [x] Удалить Grafana/Prometheus конфигурации (не существует)

### 6.3 Обновить .gitignore
- [ ] Убрать ненужные patterns
- [ ] Добавить новые (Dagster, etc.)

---

## Post-MVP: Расширения

### Дополнительные источники данных
- [ ] GitLab pipeline (`pipelines/assets/gitlab/`)
- [ ] Slack pipeline (`pipelines/assets/slack/`)
- [ ] Google Workspace (`pipelines/assets/google/`)

### Дополнительные метрики
- [ ] DORA metrics (Deployment Frequency, MTTR, etc.)
- [ ] CFD (Cumulative Flow Diagram)
- [ ] Burndown charts

### UI Improvements
- [ ] Frontend для Admin Panel (React/Vue)
- [ ] Более детальная настройка метрик

---

## Порядок выполнения (рекомендуемый)

```
Phase 0 → Phase 1 → Phase 2 → Phase 4 (tests) → Phase 3 → Phase 5 → Phase 6
```

### Минимальный MVP (только Jira + Lead Time):

1. **Phase 0.1-0.2** — pyproject.toml, docker-compose, Makefile ✅
2. **Phase 1.1** — platform.sql, clean_jira.sql (упрощённые) ✅
3. **Phase 2.1-2.2** — raw + clean assets для Jira ✅
4. **Phase 1.1** — mv_lead_time view ✅
5. **Phase 2.3** — metrics refresh asset ✅
6. **Phase 5.1** — Docker запуск ✅
7. **Phase 4** — Базовые тесты ✅

После этого: API, Metabase, остальные метрики.

---

## Чеклист готовности MVP

- [x] `docker-compose up -d` запускает все 4 контейнера
- [x] Dagster UI показывает assets (raw → clean → metrics)
- [x] Можно добавить Jira интеграцию и запустить sync
- [x] Lead Time view обновляется после sync
- [ ] `make check` проходит (lint + test + validate)
- [ ] Coverage >= 75%

---

## Примечания

- Каждая фаза завершается `make check`
- Commit после каждой логической задачи
- Не переходить к следующей фазе пока текущая не работает
- При сомнениях — упрощать, не усложнять

---
