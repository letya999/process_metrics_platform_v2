# Process Metrics Platform v2

Open-source self-hosted ETL + BI platform for engineering metrics.

## What it does

- Ingests data from Jira into PostgreSQL using `dlt`.
- Builds clean and metrics layers with Dagster assets.
- Exposes admin APIs via FastAPI.
- Renders dashboards in Metabase.

Current source in production path: Jira.
Multi-source abstraction and enterprise hardening are tracked in `techdebt.md`.

## Stack

- Python 3.11
- FastAPI
- Dagster
- PostgreSQL
- Metabase
- Docker Compose

## Quick Start (local/dev)

Prerequisites:

- Docker + Docker Compose
- Python 3.11+

Steps:

1. Clone and install dependencies:

```bash
git clone https://github.com/process-metrics-platform/process-metrics-platform-v2.git
cd process-metrics-platform-v2
cp .env.example .env
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\Activate
pip install -e ".[dev]"
```

2. Start services:

```bash
docker compose -f docker-compose.yml up -d
```

3. Run migrations:

```bash
docker compose --profile migration run --rm alembic upgrade head
```

4. Open services:

- Dagster UI: `http://localhost:3000`
- Metabase: `http://localhost:3001`
- Admin API: `http://localhost:8000`
- Admin UI (Streamlit): `http://localhost:8501`

## Quick Start (production compose)

Use `docker-compose.prod.yml` with `.env.prod` and a local `Caddyfile`:

```bash
cp .env.prod.example .env.prod
cp Caddyfile.example Caddyfile
# edit .env.prod: SERVER_IP, MB_DOMAIN, DAGSTER_DOMAIN, API_DOMAIN, ADMIN_DOMAIN, DAGSTER_BASIC_AUTH_HASH
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
docker compose -f docker-compose.prod.yml --env-file .env.prod --profile migration run --rm alembic upgrade head
```

## Runbook

Use these commands as the default quality/deploy gates:

```bash
make check
make smoke
make compose-validate
make alembic-heads
```

## Dagster automation defaults

The repository defines daily/hourly automation for the Jira pipeline and metrics refresh:

- `jira_sync_job_schedule` (`0 6 * * *`, UTC) for full `raw -> clean -> metrics`
- `metrics_refresh_job_schedule` (`0 * * * *`, UTC)
- `guarded_hourly_metrics_refresh_sensor` (hourly guard against clean/sync overlap)

Important: these schedules/sensors are created with `default_status=STOPPED` and must be enabled explicitly in Dagster UI or via CLI after deployment.

Example checks:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T dagster-daemon dagster schedule list -m pipelines.definitions
docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T dagster-daemon dagster sensor list -m pipelines.definitions
```

## Flow Efficiency configuration

`calculate_flow_efficiency` requires `metrics.calculation_settings` entries with `settings_type='flow_status_categories'` per project.

Supported config format in `settings_json`:

- preferred: explicit status IDs
  - `active_status_ids`
  - `passive_status_ids`
  - `done_status_ids`
- backward compatibility: category lists
  - `active_categories`
  - `passive_categories`
  - `done_categories`

Seed/apply script for production mappings:

```bash
cat scripts/apply_flow_status_settings.sql | docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T postgres psql -U pmp_user -d process_metrics_v2 -v ON_ERROR_STOP=1 -f -
```

Recalculate flow efficiency asset:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T dagster-daemon dagster asset materialize -m pipelines.definitions --select calculate_flow_efficiency
```

## Validation tests (DB-backed)

`tests/validation` checks are intentionally opt-in and require a running, seeded Postgres with raw/clean/metrics schemas.

```bash
make test-validation-db
# equivalent:
pytest tests/validation -v --run-db-tests
```

## Repository map

- `app/`: FastAPI app, admin and integration endpoints
- `pipelines/`: Dagster assets/jobs/schedules/calculations
- `bi/`: Metabase BI pack and metadata
- `streamlit_admin/`: admin UI
- `db/migrations/`: Alembic migrations
- `scripts/`: repo checks, smoke/validation helpers
- `tests/`: unit/integration/validation tests

## Known limitations / tech debt

See [`techdebt.md`](techdebt.md) for prioritized debt and roadmap.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Community

See [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

## License

MIT. See [`LICENSE`](LICENSE).
