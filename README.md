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
git clone <repository-url>
cd process-metrics-platform-v2
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

Use `docker-compose.prod.yml` with `.env.prod`:

```bash
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

## License

MIT. See [`LICENSE`](LICENSE).
