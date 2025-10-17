# Project Initialization Tasks

**Branch:** `chore/infrastructure-and-basement`

**Goal:** Setup repository structure, tooling, and one working service (auth_service)

**Agent Instructions:**
1. Read `.cursor/rules/*.mdc` before starting
2. One task = one commit (format: `<scope>: <description>`)
3. All tasks in single branch
4. Follow `10-core.mdc` workflow: Recon → Plan → Execute → Verify → Report

---

## Task 1: Root structure
```bash
mkdir -p services common/{loggers,errors,middleware,validators,constants,types}
mkdir -p db/{init,schemas} docker/{prometheus,grafana/dashboards} metabase tracking tests/e2e
touch tracking/.gitkeep tests/e2e/.gitkeep
```
**Commit:** `chore: initialize project structure`
**Status:** completed

---

## Task 2: .gitignore
Create with: `__pycache__/`, `*.py[cod]`, `.venv/`, `__pypackages__/`, `.pytest_cache/`, `.coverage`, `logs/`, `.env`, `tracking/*.md`

**Commit:** `chore: add .gitignore`
**Status:** completed

---

## Task 3: .env.example
```bash
POSTGRES_HOST=postgres
POSTGRES_PASSWORD=change-me-min-16-chars
REDIS_PASSWORD=change-me-min-16-chars
JWT_SECRET_KEY=change-me-min-32-chars
```
**Commit:** `chore: add .env.example`
**Status:** completed

---

## Task 4: Makefile
Targets: `help`, `lint` (black, isort, ruff), `test` (pytest --cov), `docker-build`, `docker-up`, `docker-down`, `ci` (lint + test + build), `clean`

**Commit:** `chore: add Makefile`
**Status:** completed

---

## Task 5: pytest.ini
```ini
[pytest]
testpaths = services tests
asyncio_mode = auto
addopts = --verbose --cov-report=html
```
**Commit:** `chore: add pytest configuration`
**Status:** completed

---

## Task 6: .coveragerc
Omit: `*/tests/*`, `*/migrations/*`. Exclude: `pragma: no cover`, `if TYPE_CHECKING:`

**Commit:** `chore: add coverage configuration`
**Status:** completed

---

## Task 7: .pre-commit-config.yaml
Repos: black (23.12.0), isort (5.13.2), ruff (v0.1.9), pre-commit-hooks (trailing-whitespace, end-of-file-fixer, check-yaml)

**Commit:** `chore: add pre-commit hooks`

---

## Task 8: Root pyproject.toml
Tool configs for black, isort, ruff (line-length 88, target py311)

**Commit:** `chore: add root pyproject.toml`

---

## Task 9: common/loggers/json_logger.py
`JSONFormatter` class with fields: timestamp, level, service, module, message, trace_id, user_id, extra.
`get_json_logger(service_name)` function.

**Commit:** `chore: add JSON logger`

---

## Task 10: common/errors/base_error.py
Classes: `BaseServiceError`, `NotFoundError` (404), `ValidationError` (422), `AuthenticationError` (401)

**Commit:** `chore: add base error classes`

---

## Task 11: common/constants/http_status.py
Constants: `HTTP_200_OK`, `HTTP_404_NOT_FOUND`, etc.

**Commit:** `chore: add HTTP status constants`

---

## Task 12: common/__init__.py
```python
__version__ = "1.0.0"
```
**Commit:** `chore: add package init`

---

## Task 13: auth_service structure
```bash
mkdir -p services/auth_service/app/{api,domain,infra,models/{orm,schemas},utils}
mkdir -p services/auth_service/tests/{unit,integration,fixtures}
mkdir -p services/auth_service/logs
# Add __init__.py to all packages
```
**Commit:** `chore: create service structure`

---

## Task 14: auth_service/pyproject.toml
Dependencies: fastapi, uvicorn, pydantic, sqlalchemy[asyncio], asyncpg, python-jose, passlib, httpx
Dev: black, isort, ruff. Test: pytest, pytest-asyncio, pytest-cov

**Commit:** `chore: add pyproject.toml + create service structure`

---

## Task 15: Generate requirements.txt
```bash
cd services/auth_service
pdm install
pdm export --prod --without-hashes -o requirements.txt
cd ../..
```
**Commit:** `auth: generate requirements.txt`

---

## Task 16: auth_service/.dockerignore
Include: `__pycache__/`, `.venv/`, `__pypackages__/`, `.pytest_cache/`, `.env`

**Commit:** `auth: add .dockerignore`

---

## Task 17: auth_service/Dockerfile
```dockerfile
FROM python:3.11-slim
RUN adduser --disabled-password appuser
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH"
COPY requirements.txt ./
RUN python -m venv .venv && .venv/bin/pip install -r requirements.txt
COPY app ./app
USER appuser
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')"
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8001"]
```
**Commit:** `auth: add Dockerfile`

---

## Task 18: auth_service/app/main.py
```python
from fastapi import FastAPI
from datetime import datetime

def create_app() -> FastAPI:
    app = FastAPI(title="Auth Service", version="1.0.0")
    
    @app.get("/health")
    async def health():
        return {"status": "healthy", "service": "auth_service", "timestamp": datetime.utcnow().isoformat() + "Z"}
    
    return app
```
**Commit:** `auth: add FastAPI application`

---

## Task 19: auth_service/app/config.py
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    jwt_secret_key: str
    
    model_config = {"env_file": ".env"}
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if len(self.jwt_secret_key) < 32:
            raise ValueError("JWT_SECRET_KEY must be ≥32 chars")
```
**Commit:** `auth: add configuration management`

---

## Task 20: db/init/01_create_schemas.sql
Create 15 schemas: auth, admin, etl, monitoring, orchestrator, raw_jira_*, raw_gitlab_*, clean_jira, clean_gitlab, bi_metrics, bi_dashboards, metabase
Create users: auth_user, etl_user, orchestrator_user with least privilege grants

**Commit:** `db: add schema initialization script`

---

## Task 21: docker-compose.yml
```yaml
version: '3.8'
networks:
  process_metrics_network:
services:
  postgres:
    image: postgres:15-alpine
    environment: {POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD}
    volumes: [postgres_data:/var/lib/postgresql/data, ./db/init:/docker-entrypoint-initdb.d]
    expose: ["5432"]
    healthcheck: ["CMD", "pg_isready"]
  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD}
    expose: ["6379"]
    healthcheck: ["CMD", "redis-cli", "ping"]
  auth_service:
    build: ./services/auth_service
    ports: ["8001:8001"]
    depends_on: {postgres: {condition: service_healthy}, redis: {condition: service_healthy}}
    env_file: .env
volumes:
  postgres_data:
```
**Commit:** `chore: add docker-compose.yml`

---

## Task 22: README.md
Sections: Project description, Prerequisites (Docker, Python 3.11), Quick start (cp .env.example .env, docker-compose up), Development (make commands), Architecture (link to .cursor/rules)

**Commit:** `docs: add README.md`

---

## Task 23: CONTRIBUTING.md
Sections: Setup, Branch naming (feature/, fix/, chore/), Commit format (<scope>: <description>), Testing (≥80%), PR checklist

**Commit:** `docs: add CONTRIBUTING.md`

---

## Final Verification

Test setup:
```bash
cp .env.example .env
# Edit .env with secure passwords (≥16 for DB/Redis, ≥32 for JWT)
export DOCKER_BUILDKIT=1
docker-compose build
docker-compose up -d
curl http://localhost:8001/health
# Expected: {"status":"healthy","service":"auth_service","timestamp":"..."}
```

**Check:**
- [ ] All services healthy
- [ ] Health check returns 200
- [ ] Database has 15 schemas
- [ ] `make lint` passes (after installing tools)
- [ ] `make test` passes (after adding tests)

---

**Total commits:** 23
**Services ready:** 1 (auth_service)
**Infrastructure:** Complete (Docker, Make, pytest, pre-commit, common utilities)