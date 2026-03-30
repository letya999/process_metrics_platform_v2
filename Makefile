# =============================================================================
# Process Metrics Platform - Makefile
# =============================================================================
# Main commands:
#   make check    - Run all checks (lint + test + validate)
#   make dev      - Start development environment
#   make test     - Run tests with coverage
#   make lint     - Check code style
#   make format   - Auto-format code
# =============================================================================

.PHONY: help check dev test test-unit test-integration test-validation-db lint lint-local format validate
.PHONY: migrate migrate-create migrate-down docker-build docker-up docker-down docker-logs
.PHONY: docker-reset db-reset verify setup-metabase clean install dagster-dev api-dev admin-ui-dev
.PHONY: prod-up prod-down prod-reset prod-simple-up prod-simple-down prod-simple-reset
.PHONY: smoke compose-validate alembic-heads check-prepush

# OS detection
ifeq ($(OS),Windows_NT)
    PYTHON_BIN := .venv/Scripts/python
    UVICORN_BIN := .venv/Scripts/uvicorn
    DAGSTER_BIN := .venv/Scripts/dagster
    STREAMLIT_BIN := .venv/Scripts/streamlit
    COMPOSE_ENV_PREFIX := set COMPOSE_DISABLE_ENV_FILE=1 &&
    COMPOSE_DEV_VALIDATE_PREFIX := $(COMPOSE_ENV_PREFIX) set POSTGRES_DB=process_metrics && set POSTGRES_USER=postgres && set POSTGRES_PASSWORD=postgres &&
    COMPOSE_PROD_VALIDATE_PREFIX := $(COMPOSE_ENV_PREFIX) set POSTGRES_DB=process_metrics_v2 && set POSTGRES_USER=pmp_user && set POSTGRES_PASSWORD=placeholder_password &&
else
    PYTHON_BIN := .venv/bin/python
    UVICORN_BIN := .venv/bin/uvicorn
    DAGSTER_BIN := .venv/bin/dagster
    STREAMLIT_BIN := .venv/bin/streamlit
    COMPOSE_ENV_PREFIX := COMPOSE_DISABLE_ENV_FILE=1
    COMPOSE_DEV_VALIDATE_PREFIX := COMPOSE_DISABLE_ENV_FILE=1 POSTGRES_DB=process_metrics POSTGRES_USER=postgres POSTGRES_PASSWORD=postgres
    COMPOSE_PROD_VALIDATE_PREFIX := COMPOSE_DISABLE_ENV_FILE=1 POSTGRES_DB=process_metrics_v2 POSTGRES_USER=pmp_user POSTGRES_PASSWORD=placeholder_password
endif

# Default target
.DEFAULT_GOAL := help

# Colors for terminal output
BLUE := \033[34m
GREEN := \033[32m
YELLOW := \033[33m
RED := \033[31m
NC := \033[0m  # No Color

# =============================================================================
# Help
# =============================================================================
help:
	@echo "$(BLUE)Process Metrics Platform$(NC)"
	@echo ""
	@echo "$(GREEN)Main Commands:$(NC)"
	@echo "  make check       - Run all checks: lint + test + validate"
	@echo "  make dev         - Start development environment (docker-compose up)"
	@echo "  make test        - Run pytest with coverage"
	@echo "  make test-unit   - Run only unit tests"
	@echo "  make test-integration - Run only integration tests"
	@echo "  make test-validation-db - Run DB-backed validation tests (requires seeded DB)"
	@echo "  make smoke       - Run minimal smoke test gate"
	@echo "  make lint        - Check code style (ruff + black + policy)"
	@echo "  make lint-local  - Check code style only for changed Python files"
	@echo "  make format      - Auto-format code (ruff --fix + black)"
	@echo "  make validate    - Run data validation checks"
	@echo "  make check-prepush - Run pre-push quality gates"
	@echo ""
	@echo "$(GREEN)Database:$(NC)"
	@echo "  make migrate         - Run Alembic migrations (upgrade head)"
	@echo "  make migrate-create  - Create new migration (MSG required)"
	@echo "  make migrate-down    - Rollback one migration"
	@echo "  make alembic-heads   - Ensure a single Alembic head exists"
	@echo ""
	@echo "$(GREEN)Docker:$(NC)"
	@echo "  make docker-build    - Build all Docker images"
	@echo "  make docker-up       - Start all services"
	@echo "  make docker-down     - Stop all services"
	@echo "  make docker-logs     - View service logs"
	@echo "  make docker-reset    - Remove volumes (DESTRUCTIVE)"
	@echo "  make compose-validate - Validate docker compose manifests"
	@echo "  make db-reset        - Full DB reset + init (DESTRUCTIVE)"
	@echo "  make prod-up         - Start production stack (docker-compose.prod.yml)"
	@echo "  make prod-down       - Stop production stack"
	@echo "  make prod-reset      - Reset production stack with volumes (DESTRUCTIVE)"
	@echo "  make verify          - Verify MVP setup is correct"
	@echo ""
	@echo "$(GREEN)Development:$(NC)"
	@echo "  make install         - Install Python dependencies"
	@echo "  make clean           - Clean build artifacts"
	@echo "  make dagster-dev     - Run Dagster locally"
	@echo "  make api-dev         - Run FastAPI locally"
	@echo "  make admin-ui-dev    - Run Streamlit Admin UI locally"

# =============================================================================
# Main Commands
# =============================================================================

## Run all checks before commit: lint + test + validate
check: lint test validate
	@echo "$(GREEN)All checks passed!$(NC)"

## Start development environment
dev: docker-up
	@echo "$(GREEN)Development environment started!$(NC)"
	@echo "  - Admin API:   http://localhost:8000"
	@echo "  - Admin UI:    http://localhost:8501"
	@echo "  - Dagster UI:  http://localhost:3000"
	@echo "  - Metabase:    http://localhost:3001"

## Setup Metabase (create admin & metrics dashboards)
setup-metabase:
	@echo "$(BLUE)Setting up Metabase...$(NC)"
	docker compose up --build  metabase-init
	@echo "$(GREEN)Metabase configured!$(NC)"


## Run tests with coverage
test:
	@echo "$(BLUE)Running tests...$(NC)"
	$(PYTHON_BIN) -m pytest tests/ -v --cov=app --cov=pipelines --cov-report=term-missing
	@echo "$(GREEN)Tests passed!$(NC)"

## Run only unit tests
test-unit:
	@echo "$(BLUE)Running unit tests...$(NC)"
	$(PYTHON_BIN) -m pytest tests/unit -v
	@echo "$(GREEN)Unit tests passed!$(NC)"

## Run only integration tests
test-integration:
	@echo "$(BLUE)Running integration tests...$(NC)"
	$(PYTHON_BIN) -m pytest tests/integration -v
	@echo "$(GREEN)Integration tests passed!$(NC)"

## Run DB-backed validation tests (requires live DB and seeded data)
test-validation-db:
	@echo "$(BLUE)Running validation tests with --run-db-tests...$(NC)"
	$(PYTHON_BIN) -m pytest tests/validation -v --run-db-tests
	@echo "$(GREEN)Validation tests passed!$(NC)"

## Run minimal smoke tests for fast quality gate
smoke:
	@echo "$(BLUE)Running smoke test gate...$(NC)"
	$(PYTHON_BIN) scripts/run_smoke_tests.py
	@echo "$(GREEN)Smoke tests passed!$(NC)"

## Check code style with ruff and black
lint:
	@echo "$(BLUE)Checking code style...$(NC)"
	$(PYTHON_BIN) -m ruff check app/ pipelines/ streamlit_admin/ bi/ scripts/ tests/
	$(PYTHON_BIN) -m black --check app/ pipelines/ streamlit_admin/ bi/ scripts/ tests/
	$(PYTHON_BIN) scripts/check_repo_policy.py
	@echo "$(GREEN)Linting passed!$(NC)"

## Check style for changed Python files only (local workflow)
lint-local:
	@echo "$(BLUE)Checking changed Python files...$(NC)"
	$(PYTHON_BIN) scripts/lint_local.py
	@echo "$(GREEN)Local lint complete!$(NC)"

## Auto-format code with ruff and black
format:
	@echo "$(BLUE)Formatting code...$(NC)"
	$(PYTHON_BIN) -m ruff check --fix app/ pipelines/ streamlit_admin/ bi/ scripts/ tests/
	$(PYTHON_BIN) -m black app/ pipelines/ streamlit_admin/ bi/ scripts/ tests/
	@echo "$(GREEN)Code formatted!$(NC)"

## Run data validation checks
validate:
	@echo "$(BLUE)Running data validation...$(NC)"
	$(PYTHON_BIN) scripts/run_validation.py
	@echo "$(GREEN)Validation complete!$(NC)"

## Pre-push quality gate: fast comprehensive checks
check-prepush: lint-local smoke compose-validate
	@echo "$(GREEN)Pre-push checks passed!$(NC)"

# =============================================================================
# Database Commands
# =============================================================================

## Run Alembic migrations (upgrade head)
migrate:
	@echo "$(BLUE)Running database migrations...$(NC)"
	docker compose --profile migration run --rm alembic upgrade head
	@echo "$(GREEN)Migrations complete!$(NC)"

## Create new migration (use: make migrate-create MSG="description")
migrate-create:
	$(if $(strip $(MSG)),,$(error MSG is required. Usage: make migrate-create MSG="description"))
	@echo "$(BLUE)Creating migration: $(MSG)$(NC)"
	docker compose --profile migration run --rm alembic revision --autogenerate -m "$(MSG)"
	@echo "$(GREEN)Migration created!$(NC)"

## Rollback one migration
migrate-down:
	@echo "$(BLUE)Rolling back migration...$(NC)"
	docker compose --profile migration run --rm alembic downgrade -1
	@echo "$(GREEN)Rollback complete!$(NC)"

## Ensure a single Alembic head to avoid migration divergence
alembic-heads:
	@echo "$(BLUE)Checking Alembic heads...$(NC)"
	$(PYTHON_BIN) scripts/check_alembic_heads.py
	@echo "$(GREEN)Alembic heads check complete!$(NC)"

# =============================================================================
# Docker Commands
# =============================================================================

## Build all Docker images
docker-build:
	@echo "$(BLUE)Building Docker images...$(NC)"
	DOCKER_BUILDKIT=1 docker compose build --parallel
	@echo "$(GREEN)Build complete!$(NC)"

## Start all services
docker-up:
	@echo "$(BLUE)Starting services...$(NC)"
	docker compose up -d
	@echo "$(GREEN)Services started!$(NC)"

## Stop all services
docker-down:
	@echo "$(BLUE)Stopping services...$(NC)"
	docker compose down
	@echo "$(GREEN)Services stopped!$(NC)"

## Validate docker compose manifests
compose-validate:
	@echo "$(BLUE)Validating docker compose manifests...$(NC)"
	$(COMPOSE_DEV_VALIDATE_PREFIX) docker compose -f docker-compose.yml --env-file .env.example config -q
	$(COMPOSE_PROD_VALIDATE_PREFIX) docker compose -f docker-compose.prod.yml --env-file .env.prod.example config -q
	@echo "$(GREEN)Compose manifests are valid!$(NC)"

## Start production stack
prod-up:
	@echo "$(BLUE)Starting services in PRODUCTION mode...$(NC)"
	docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
	@echo "$(BLUE)Running database migrations...$(NC)"
	docker compose -f docker-compose.prod.yml --env-file .env.prod --profile migration run --rm alembic upgrade head
	@echo "$(GREEN)Services started and migrated in PRODUCTION mode!$(NC)"

## Stop production stack
prod-down:
	@echo "$(BLUE)Stopping PRODUCTION services...$(NC)"
	docker compose -f docker-compose.prod.yml --env-file .env.prod down
	@echo "$(GREEN)Services stopped!$(NC)"

## Reset production stack with volume cleanup (DESTRUCTIVE)
prod-reset:
	@echo "$(RED)WARNING: This will delete ALL data in PRODUCTION mode!$(NC)"
	docker compose -f docker-compose.prod.yml --env-file .env.prod down -v --remove-orphans
	@echo "$(BLUE)Building and starting services...$(NC)"
	docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
	@echo "$(BLUE)Waiting for Postgres to be ready and running migrations...$(NC)"
	docker compose -f docker-compose.prod.yml --env-file .env.prod --profile migration run --rm alembic upgrade head
	@echo "$(GREEN)Production-test environment reset and ready from scratch!$(NC)"

## Backward-compatible aliases
prod-simple-up: prod-up
prod-simple-down: prod-down
prod-simple-reset: prod-reset

## View service logs (follow mode)
docker-logs:
	docker compose logs -f

## Stop services and remove volumes (DESTRUCTIVE)
docker-reset:
	@echo "$(RED)WARNING: This will delete all data!$(NC)"
	docker compose down -v
	@echo "$(GREEN)Reset complete!$(NC)"

## Full reset: delete volume, rebuild, and init database (DESTRUCTIVE)
db-reset: docker-reset docker-build docker-up migrate
	@echo "$(GREEN)Database fully reset and initialized!$(NC)"

## Verify MVP setup is correct
verify:
	@echo "$(BLUE)Verifying MVP setup...$(NC)"
	@bash scripts/verify_setup.sh || sh scripts/verify_setup.sh
	@echo "$(GREEN)Verification complete!$(NC)"

# =============================================================================
# Development Commands
# =============================================================================

## Install Python dependencies
install:
	@echo "$(BLUE)Installing dependencies...$(NC)"
	$(PYTHON_BIN) -m pip install -e ".[dev]"
	@echo "$(GREEN)Installation complete!$(NC)"

## Clean build artifacts
clean:
	@echo "$(BLUE)Cleaning build artifacts...$(NC)"
	$(PYTHON_BIN) -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]"
	$(PYTHON_BIN) -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('.pytest_cache')]"
	$(PYTHON_BIN) -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in [pathlib.Path('.coverage'), pathlib.Path('htmlcov'), pathlib.Path('.ruff_cache'), pathlib.Path('.mypy_cache'), pathlib.Path('build'), pathlib.Path('dist'), pathlib.Path('.dagster')]]"
	$(PYTHON_BIN) -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('*.egg-info')]"
	@echo "$(GREEN)Clean complete!$(NC)"

## Run Dagster locally (for development without Docker)
dagster-dev:
	@echo "$(BLUE)Starting Dagster dev server...$(NC)"
	$(DAGSTER_BIN) dev -m pipelines.definitions

## Run FastAPI locally (for development without Docker)
api-dev:
	@echo "$(BLUE)Starting FastAPI dev server...$(NC)"
	$(UVICORN_BIN) app.main:app --reload --host 0.0.0.0 --port 8000

## Run Streamlit Admin UI locally (for development without Docker)
admin-ui-dev:
	@echo "$(BLUE)Starting Streamlit Admin UI...$(NC)"
	$(STREAMLIT_BIN) run streamlit_admin/app.py --server.port=8501 --server.address=0.0.0.0
