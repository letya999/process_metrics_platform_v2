# CLAUDE.md - Process Metrics Platform v2

## Project Overview

**Process Metrics Platform** is an open-source, self-hosted ETL + BI platform for calculating and visualizing software development team metrics (Lead Time, Velocity, Throughput, DORA metrics).

**Target users:** Project managers, delivery managers, agile coaches, team leads.

## Quick Start

```bash
# Start all services
docker-compose up -d

# Run migrations
docker-compose exec app alembic upgrade head

# Open services
# - Admin Panel: http://localhost:8000
# - Dagster UI: http://localhost:3000
# - Metabase: http://localhost:3001
```

## Architecture

### Monolith approach (not microservices)

```
┌─────────────────────────────────────────────────┐
│              Docker Compose                      │
│                                                  │
│  ┌────────────┐  ┌────────────┐  ┌──────────┐  │
│  │  Dagster   │  │  FastAPI   │  │ Metabase │  │
│  │  :3000     │  │  :8000     │  │  :3001   │  │
│  └────────────┘  └────────────┘  └──────────┘  │
│                                                  │
│  ┌────────────────────────────────────────────┐ │
│  │              PostgreSQL                     │ │
│  │  raw_* → clean_* → metrics (views)         │ │
│  └────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

### Data layers (Medallion architecture)

| Layer | Schema | Purpose |
|-------|--------|---------|
| **Raw (Bronze)** | `raw_jira`, `raw_gitlab` | Append-only, dlt loads data as-is |
| **Clean (Silver)** | `clean_jira`, `clean_gitlab` | Normalized, untangled structure |
| **Metrics (Gold)** | `metrics` | Materialized views for BI |
| **Platform** | `platform` | Users, integrations, configs |

### Tech Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Orchestration** | Dagster | Pipeline scheduling, UI, asset lineage |
| **Data Ingestion** | dlt | Extract from Jira, GitLab, Slack |
| **API** | FastAPI | Admin panel backend |
| **Database** | PostgreSQL 15 | All data storage |
| **BI** | Metabase | Dashboards and visualizations |
| **Language** | Python 3.11 | Runtime |

## Project Structure

```
process_metrics/
├── app/                          # FastAPI admin API
│   ├── main.py                   # App entrypoint
│   ├── api/                      # API routes
│   │   ├── integrations.py       # CRUD for data sources
│   │   ├── projects.py           # Project selection
│   │   └── metric_config.py      # Metric configuration
│   ├── models/
│   │   └── orm.py                # SQLAlchemy models (platform schema)
│   └── services/
│       └── dagster_client.py     # Trigger Dagster jobs
│
├── pipelines/                    # Dagster pipelines
│   ├── definitions.py            # Dagster Definitions entry
│   ├── assets/
│   │   ├── jira/
│   │   │   ├── raw.py            # dlt → raw_jira
│   │   │   └── clean.py          # raw → clean_jira
│   │   ├── gitlab/
│   │   │   ├── raw.py
│   │   │   └── clean.py
│   │   └── metrics/
│   │       └── views.py          # Refresh materialized views
│   ├── resources/
│   │   └── database.py           # DB resource
│   └── jobs/
│       └── schedules.py          # Cron schedules
│
├── db/
│   ├── migrations/               # Alembic migrations
│   ├── schemas/
│   │   ├── platform.sql          # Users, integrations, configs
│   │   └── clean_jira.sql        # Clean Jira schema
│   └── views/
│       └── metrics.sql           # Materialized views
│
├── tests/
│   ├── unit/
│   └── integration/
│
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
└── CLAUDE.md                     # This file
```

## Common Commands

```bash
# Development
make dev                    # Start dev environment
make test                   # Run all tests
make lint                   # Run linters (ruff, black)
make format                 # Auto-format code

# Database
make migrate                # Run Alembic migrations
make migrate-create MSG="description"  # Create new migration

# Dagster
dagster dev                 # Start Dagster dev server
dagster job execute -j jira_sync_job  # Run job manually

# Docker
docker-compose up -d        # Start all services
docker-compose logs -f app  # View logs
docker-compose down         # Stop services
```

## Key Concepts

### Dagster Assets

Assets represent data artifacts. Dependencies are explicit:

```python
@asset(group_name="jira")
def raw_jira_issues():
    """Load from Jira API to raw layer."""
    pass

@asset(deps=[raw_jira_issues])
def clean_jira_issues():
    """Transform raw to clean layer."""
    pass

@asset(deps=[clean_jira_issues])
def metrics_lead_time():
    """Refresh lead time materialized view."""
    pass
```

### dlt Pipelines

dlt handles incremental loading and state:

```python
pipeline = dlt.pipeline(
    pipeline_name="jira",
    destination="postgres",
    dataset_name="raw_jira"
)

source = jira_source(projects=["PROJ1", "PROJ2"])
pipeline.run(source, write_disposition="append")
```

### Data Flow

```
Jira API → dlt → raw_jira (append-only)
                    ↓
              clean_jira (normalized)
                    ↓
              metrics.mv_* (materialized views)
                    ↓
              Metabase (dashboards)
```

## Configuration

Environment variables (`.env`):

```bash
# Database
DATABASE_URL=postgresql://postgres:pass@localhost:5432/metrics

# Jira
JIRA_BASE_URL=https://company.atlassian.net
JIRA_USER_EMAIL=user@company.com
JIRA_API_TOKEN=secret

# Dagster
DAGSTER_HOME=/app/.dagster
```

## Adding New Data Source

1. Create dlt source in `pipelines/assets/{source}/raw.py`
2. Create clean transformation in `pipelines/assets/{source}/clean.py`
3. Add SQL schema in `db/schemas/clean_{source}.sql`
4. Update metrics views if needed
5. Register assets in `pipelines/definitions.py`

## Code Style

- Python 3.11+ with type hints
- Formatting: `black` (88 chars), `isort`
- Linting: `ruff`
- Testing: `pytest`, `pytest-asyncio`
- SQL: lowercase keywords, snake_case names

## Testing

```bash
# Unit tests (fast, no DB)
pytest tests/unit/

# Integration tests (with DB)
pytest tests/integration/

# With coverage
pytest --cov=app --cov=pipelines
```

## Troubleshooting

### Dagster job fails
1. Check Dagster UI logs at http://localhost:3000
2. Verify credentials in `.env`
3. Check database connectivity

### dlt incremental not working
1. Check `_dlt_loads` table for state
2. Verify `primary_key` is set on resource
3. Check `write_disposition` setting

### Materialized view stale
```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY metrics.mv_lead_time;
```
