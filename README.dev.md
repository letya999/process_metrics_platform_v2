# Prefect + DLT: минимальный надёжный стек (локально)

Кратко:
- Авто-регистрация деплоев при старте (init-контейнер `prefect-deploy-init`).
- Prefect Server v3 c расписанием (cron).
- Worker(ы) исполняют деплои; DLT пишет в Postgres (dataset = schema в БД).
- Jira креды берём из `platform.tool_integrations` (токен только в ENV), инкрементальность хранит DLT (без дубляжа в БД).
- (Опционально) метрики пишем в `platform.pipeline_runs`.

## 1) Подготовка
1. Создайте `.env` в корне (не коммитим):
```
POSTGRES_DB=process_metrics_v2
POSTGRES_USER=postgres
POSTGRES_PASSWORD=... # >=16 символов
REDIS_PASSWORD=...    # >=16 символов
# Пул для DLT-воркера (можно оставить default)
DLT_WORK_POOL=dlt
PREFECT_WORK_POOL=default
# Токен Jira живёт только в ENV, имя переменной вы сами задаёте
JIRA_API_TOKEN_MAIN=...  # сам токен, не сохраняйте его в БД
```

2. (Опционально) Заведите integration и project напрямую SQL-ом:
```sql
-- тип интеграции есть в platform.integration_types (jira_cloud)
-- создаём интеграцию с секретом по ссылке на ENV
INSERT INTO platform.tool_integrations (
  id, user_id, integration_type_id, instance_url, user_email,
  secret_reference, secret_provider, is_active
)
SELECT gen_random_uuid(), u.id, it.id, 'https://your-domain.atlassian.net', 'user@example.com',
       'JIRA_API_TOKEN_MAIN', 'env', TRUE
FROM platform.users u
JOIN platform.integration_types it ON it.name = 'jira_cloud'
LIMIT 1
RETURNING id;  -- запомните UUID интеграции

-- проект, связанный с интеграцией
INSERT INTO platform.projects (
  id, owner_user_id, tool_integration_id, external_key, external_id, name, external_url
)
VALUES (
  gen_random_uuid(), (SELECT id FROM platform.users LIMIT 1), '<TOOL_INTEGRATION_ID>',
  'PROJ', '10000', 'Demo Project', 'https://your-domain.atlassian.net/jira/projects/PROJ'
);
```

## 2) Сборка и запуск
```
make docker-build
make up-core   # поднимет postgres/redis/prefect + deploy-init и 2 воркера
```
Проверьте, что init-контейнер завершился успешно:
```
docker compose logs -f prefect-deploy-init
```

Список деплоев Prefect:
```
docker compose exec dlt_jira_worker prefect deployments ls
```
Должны быть как минимум:
- `jira-sync-manual-<env>`
- `jira-sync-daily-<env>` (cron 02:00 UTC)

## 3) Ручной запуск и проверка
Запустить вручную:
```
docker compose exec dlt_jira_worker prefect deployment run 'jira_sync_flow/jira-sync-manual-development'
```
Логи воркера:
```
docker compose logs -f dlt_jira_worker
```
Проверить, что есть запись про метрики выполнения:
```
docker compose exec postgres psql -U postgres -d process_metrics_v2 -c \
  "SELECT status, created_at, metrics FROM platform.pipeline_runs ORDER BY created_at DESC LIMIT 5;"
```

(Если включить реальную загрузку)
```
docker compose exec dlt_jira_worker bash -lc 'export DLT_ENABLE_REAL_RUN=1; prefect worker preview' # для отладки
```
DLT пишет в Postgres (schema = `dataset_name`). По умолчанию из кода — `raw_jira_cloud_dlt`.
Можно передать другой `dataset_name` через конфиг flow.

## 4) Как работают креды и секреты
- В `platform.tool_integrations` хранится только `secret_reference` (имя ENV) и `secret_provider='env'`.
- Токен берётся функцией резолвера из ENV во время выполнения flow и в БД не сохраняется/не логируется.
- Остальные поля (`instance_url`, `user_email`) берутся из той же таблицы и передаются в DLT.

## 5) Пулы/воркеры
- Пулы создаются автоматически при деплое, если их нет (`default`, `dlt`).
- Конкурентность ограничена переменной `PREFECT_WORKER_CONCURRENCY` (по умолчанию 2).
- `dlt_jira_worker` слушает пул `${DLT_WORK_POOL:-dlt}`; общий `prefect-worker` — `${PREFECT_WORK_POOL:-default}`.

## 6) Дымовые проверки
1. `docker compose ps` — все healthy, `prefect-deploy-init` в `Exited (0)`.
2. `prefect deployments ls` — деплои на месте.
3. Запустите один run — смотрите логи воркера.
4. Проверьте `platform.pipeline_runs` (метрики/статус).
5. При `DLT_ENABLE_REAL_RUN=1` проверьте, что таблицы появились в целевой схеме (`SELECT * FROM information_schema.tables WHERE table_schema='raw_jira_cloud_dlt';`).

## 7) FAQ
- Инкрементальность: первична DLT state. Таблица `integration_sync_checkpoints` оставлена как legacy/read-only, новые flow её не трогают.
- Где менять крон: сейчас жёстко в `services/dlt_jira_loader/deployments/deploy.py` (02:00 UTC). Можно вынести в ENV.
- Куда писать: Postgres подключение берётся из `DB_HOST/DB_NAME/DB_USER/DB_PASSWORD` (см. `docker-compose.yml`).
