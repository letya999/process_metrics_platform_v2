# BI Providers

`/bi` contains BI providers and versions of ready-made dashboard packs.

## Goals

- Metabase is one of the providers, not the only hardcoded option.
- Dashboard-as-code: cards/dashboards are stored in Git as JSON specs.
- Idempotent provisioning via API (no dependency on transferring IDs between instances).

## Structure

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

## Running

```bash
python -m bi.main --provider metabase --pack process_metrics_v1
```

## Verifying pack cards on a real Metabase

```bash
python bi/verify_metabase_pack.py --provider metabase --pack process_metrics_v1 --url http://localhost:3001
```

## Adding a new BI provider

1. Create `bi/providers/<provider>/provider.py` with a `provision(pack_dir: Path)` method.
2. Add the provider to `bi/registry.py`.
3. Place pack specs in `bi/packs/<provider>/<pack_name>/`.

## Environment Variables for Metabase

- `METABASE_URL`
- `METABASE_API_KEY` (optional)
- `MB_ADMIN_EMAIL` / `MB_ADMIN_PASSWORD`
- `MB_SITE_NAME` (optional)
- `BI_DATABASE_NAME` / `BI_DATABASE_ENGINE` / `BI_DATABASE_SCHEMA` / `BI_DATABASE_SSL`
- `POSTGRES_HOST` / `POSTGRES_PORT` / `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD`
