# BI Providers

`/bi` содержит поставщиков BI и версии готовых паков дашбордов.

## Цели

- Metabase является одним из провайдеров, а не единственным hardcoded вариантом.
- Dashboard-as-code: карточки/дашборды хранятся в Git как JSON-спеки.
- Идемпотентный provisioning через API (без зависимости на перенос ID между инстансами).

## Структура

```text
bi/
  main.py
  provider_base.py
  registry.py
  providers/
    metabase/
      client.py
      provider.py
  packs/
    metabase/
      process_metrics_v1/
        collections.json
        cards/*.json
        dashboards/*.json
```

## Запуск

```bash
python -m bi.main --provider metabase --pack process_metrics_v1
```

## Проверка карточек pack на реальном Metabase

```bash
python bi/verify_metabase_pack.py --provider metabase --pack process_metrics_v1 --url http://localhost:3001
```

## Добавление нового BI-провайдера

1. Создать `bi/providers/<provider>/provider.py` с методом `provision(pack_dir: Path)`.
2. Добавить провайдера в `bi/registry.py`.
3. Положить pack-спеки в `bi/packs/<provider>/<pack_name>/`.

## Переменные окружения для Metabase

- `METABASE_URL`
- `METABASE_API_KEY` (опционально)
- `MB_ADMIN_EMAIL` / `MB_ADMIN_PASSWORD`
- `MB_SITE_NAME` (опционально)
- `BI_DATABASE_NAME` / `BI_DATABASE_ENGINE` / `BI_DATABASE_SCHEMA` / `BI_DATABASE_SSL`
- `POSTGRES_HOST` / `POSTGRES_PORT` / `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD`
