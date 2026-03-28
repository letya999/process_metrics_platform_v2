# Process Metrics Platform v2

**Open-source, self-hosted ETL + BI platform for software development teams.**

[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com)
[![Dagster](https://img.shields.io/badge/Dagster-1.9-purple.svg)](https://dagster.io)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Calculate and visualize key engineering metrics (Velocity, Lead Time, DORA) from your tools (Jira, GitLab) without sending data to the cloud.

---

## 🚀 Key Features

- **Self-Hosted & Private**: Your data never leaves your server (100% on-premise/VPS).
- **Modern Stack**:
  - **Ingestion**: [dlt](https://dlthub.com) for robust data extraction (Jira, GitLab, Slack).
  - **Orchestration**: [Dagster](https://dagster.io) for reliable data pipelines and asset management.
  - **API**: [FastAPI](https://fastapi.tiangolo.com) for admin management.
  - **BI & Dashboards**: [Metabase](https://www.metabase.com) for visualization.
  - **Infrastructure**: Docker Compose + Caddy (automatic HTTPS) + PostgreSQL.
- **Pre-built Metrics**:
  - **Scrum**: Velocity, Sprint Burndown, Predictability.
  - **Kanban**: Lead Time, Cycle Time, Throughput, CFD.
  - **DORA**: Deployment Frequency, Lead Time for Changes (in progress).

## 🛠️ Quick Start (Production)

For a simple robust deployment on a single server (e.g., DigitalOcean Droplet):

👉 **[Read the Contributing Guide](CONTRIBUTING.md)**

Summary:
1. **Clone** the repo.
2. **Configure** `.env` (generated secure passwords + Jira credentials).
3. **Run**:
   ```bash
   docker compose -f docker-compose.simple.yml up -d
   ```
4. **Access**:
   - 📊 **Dashboards (Metabase)**: `https://metrics.your-domain.com`
   - ⚙️ **Pipelines (Dagster)**: `https://dagster.your-domain.com`
   - 🔧 **Admin API**: `https://api.your-domain.com`

## 💻 Development Setup

### Prerequisites
- Python 3.11+
- Docker & Docker Compose
- `make` (optional, for convenience)

### Installation

1. **Clone and Setup Environment**:
   ```bash
   git clone https://github.com/<your-github-user-or-org>/process-metrics-platform-v2.git
   cd process-metrics-platform-v2

   # Setup virtualenv and dependencies
   python -m venv .venv
   source .venv/bin/activate  # or .venv\Scripts\Activate on Windows
   pip install -e ".[dev]"
   ```

2. **Start Dev Stack**:
   ```bash
   # Starts Postgres, Dagster, Metabase locally
   docker compose up -d
   ```

3. **Run Checks**:
   ```bash
   make check  # Runs Lint + Test + Validate
   ```

## 🏗️ Architecture

```mermaid
graph TD
    Sources[Jira / GitLab / Slack] -->|dlt| Raw[Raw Layer (Bronze)]
    Raw -->|Dagster| Clean[Clean Layer (Silver)]
    Clean -->|SQL/dbt| Metrics[Metrics Layer (Gold)]
    Metrics -->|SQL| Metabase[Metabase Dashboards]

    subgraph "Docker Compose Host"
        Raw
        Clean
        Metrics
        Metabase
        FastAPI[Admin API]
    end
```

## 📚 Documentation

- **[Contributing Guide](CONTRIBUTING.md)**: Local setup and development workflow.
- **[Security Policy](SECURITY.md)**: How to report vulnerabilities.

## Security Migration Notes

If you are upgrading to this version, review these environment variables:

- `ADMIN_AUTH_SECRET` or `SECRET_KEY` (required for admin token signing).
- `ADMIN_AUTH_TTL_MINUTES` (default `120`, allowed range `5..1440`).
- `ADMIN_TOKENS_INVALID_BEFORE` (optional global token revocation cutover; unix timestamp or ISO8601).
- `INTEGRATION_ALLOWED_URL_SCHEMES` (default `https`).
- `INTEGRATION_ALLOWED_HOST_PATTERNS` (optional host glob allowlist for integration URLs).
- `INTEGRATION_ALLOW_PRIVATE_IPS` (default `true`, useful for internal networks).
- `INTEGRATION_ALLOW_LOCALHOST` (default `false`).

Recommended baseline for closed internal deployments:

- Keep `INTEGRATION_ALLOWED_URL_SCHEMES=https`.
- Define `INTEGRATION_ALLOWED_HOST_PATTERNS` for known domains where possible.
- Keep `INTEGRATION_ALLOW_LOCALHOST=false` unless explicitly required.
- Set a non-empty `ADMIN_AUTH_SECRET` and rotate it on incident.

## 🤝 Contributing

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.
