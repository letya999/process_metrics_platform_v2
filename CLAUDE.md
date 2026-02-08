# CLAUDE.md - Process Metrics Platform v2

## Project Overview

**Process Metrics Platform** is an open-source, self-hosted ETL + BI platform for calculating and visualizing software development team metrics (Lead Time, Velocity, Throughput, DORA metrics).

**Target users:** Project managers, delivery managers, agile coaches, team leads.
**Core philosophy:** Simple, self-hosted, monolith over microservices.

## Quick Start (Production / Self-Hosted)

Based on **[SIMPLE_DEPLOY_GUIDE.md](docs/SIMPLE_DEPLOY_GUIDE.md)**:

### 1. Configure & Start
```bash
# 1. Prepare env
cp .env.example .env.production
# Edit .env.production with secure passwords and Jira credentials

# 2. Run with Caddy (Automatic HTTPS)
docker compose -f docker-compose.simple.yml up -d
```

### 2. Access Services
- **Metabase (BI):** `https://metrics.your-domain.com`
- **Dagster (ETL):** `https://dagster.your-domain.com`
- **Admin API:** `https://api.your-domain.com`

---

## Development Workflow

### 1. Start Dev Environment
```bash
make dev  # Starts docker-compose up -d (standard)
```

### 2. Common Commands (Makefile)
```bash
# Main
make check                  # ⚡ Run ALL checks (Lint + Test + Validate)

# Individual
make test                   # Run pytest (Unit + Integration)
make lint                   # Run ruff + black (Check only)
make format                 # Auto-fix code (ruff --fix + black)
make validate               # Run data integrity checks
make migrate                # Apply DB migrations (Alembic)
make migrate-create MSG="x" # Create new migration
```

### 3. Data Flow (Medallion Architecture)
```
Jira/GitLab API
   ↓ (dlt)
RAW Layer (Bronze)   → JSON, append-only
   ↓ (Dagster Asset)
CLEAN Layer (Silver) → Normalized tables, typed
   ↓ (SQL View)
METRICS Layer (Gold) → Materialized views, aggregated
   ↓ (SQL)
Metabase             → Visualizations
```

## Architecture & Stack

### Tech Stack
| Component | Technology | Purpose |
|-----------|------------|---------|
| **Orchestration** | Dagster | Pipeline scheduling, UI, asset lineage |
| **Ingestion** | dlt | Extract from Jira, GitLab, Slack |
| **API** | FastAPI | Admin panel backend |
| **Database** | PostgreSQL 15 | All data storage |
| **BI** | Metabase | Dashboards and visualizations |
| **Proxy** | Caddy | Automatic HTTPS, Reverse Proxy |
| **Language** | Python 3.11 | Runtime |

### Key Directories
- `app/` - FastAPI backend (Admin API)
- `pipelines/` - Dagster assets and jobs
  - `assets/` - Data transformations (raw -> clean -> metrics)
- `db/` - SQL schemas and migrations
- `docs/` - Documentation (Deployment, Audit)
- `tests/` - Unit and Integration tests

## Testing & Quality

### Rules
- **Coverage:** Minimum **75%** overall.
- **Linting:** Zero tolerance (enforced by `ruff` and `black`).
- **Data Validation:** Critical. Run `make validate` after schema changes.

### Running Tests
```bash
pytest tests/unit/ -v        # Fast unit tests
pytest tests/integration/ -v # DB-dependent tests
pytest --cov                 # Check coverage
```

## configuration

**Environment Variables** (`.env`):
- `DATABASE_URL`: Postgres connection
- `JIRA_*`: Credentials for ingestion
- `DAGSTER_HOME`: Path for Dagster state

## Troubleshooting

- **Dagster fails:** Check `docker compose logs dagster` and Jira credentials.
- **DB connectivity:** Check `docker compose logs postgres`.
- **HTTPS issues:** Check `docker compose -f docker-compose.simple.yml logs caddy`.

## Recent Changes (Feb 2026)
- **Simplified Deployment:** Single Docker Compose file (`docker-compose.simple.yml`) with Caddy.
- **Security:** Added HTTPS, Firewall rules guide, and CORS white-listing.
- **Audit:** Architecture validated as robust for self-hosting.
