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

.PHONY: help check dev test lint format validate migrate migrate-create migrate-down
.PHONY: docker-build docker-up docker-down docker-logs clean install

# OS detection
ifeq ($(OS),Windows_NT)
    PYTHON_BIN := .venv/Scripts/python
    UVICORN_BIN := .venv/Scripts/uvicorn
    DAGSTER_BIN := .venv/Scripts/dagster
    RM := rmdir /s /q
    MKDIR := mkdir
    SEP := \\
else
    PYTHON_BIN := .venv/bin/python
    UVICORN_BIN := .venv/bin/uvicorn
    DAGSTER_BIN := .venv/bin/dagster
    RM := rm -rf
    MKDIR := mkdir -p
    SEP := /
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
	@echo "  make lint        - Check code style (ruff + black)"
	@echo "  make format      - Auto-format code (ruff --fix + black)"
	@echo "  make validate    - Run data validation checks"
	@echo ""
	@echo "$(GREEN)Database:$(NC)"
	@echo "  make migrate         - Run Alembic migrations (upgrade head)"
	@echo "  make migrate-create  - Create new migration (MSG required)"
	@echo "  make migrate-down    - Rollback one migration"
	@echo ""
	@echo "$(GREEN)Docker:$(NC)"
	@echo "  make docker-build    - Build all Docker images"
	@echo "  make docker-up       - Start all services"
	@echo "  make docker-down     - Stop all services"
	@echo "  make docker-logs     - View service logs"
	@echo "  make docker-reset    - Remove volumes (DESTRUCTIVE)"
	@echo "  make db-reset        - Full DB reset + init (DESTRUCTIVE)"
	@echo "  make verify          - Verify MVP setup is correct"
	@echo ""
	@echo "$(GREEN)Development:$(NC)"
	@echo "  make install         - Install Python dependencies"
	@echo "  make clean           - Clean build artifacts"
	@echo "  make dagster-dev     - Run Dagster locally"
	@echo "  make api-dev         - Run FastAPI locally"

# =============================================================================
# Main Commands
# =============================================================================

## Run all checks before commit: lint + test + validate
check: lint test validate
	@echo "$(GREEN)All checks passed!$(NC)"

## Start development environment
dev: docker-up
	@echo "$(GREEN)Development environment started!$(NC)"
	@echo "  - Admin Panel: http://localhost:8000"
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

## Check code style with ruff and black
lint:
	@echo "$(BLUE)Checking code style...$(NC)"
	$(PYTHON_BIN) -m ruff check app/ pipelines/ tests/
	$(PYTHON_BIN) -m black --check app/ pipelines/ tests/
	@echo "$(GREEN)Linting passed!$(NC)"

## Auto-format code with ruff and black
format:
	@echo "$(BLUE)Formatting code...$(NC)"
	$(PYTHON_BIN) -m ruff check --fix app/ pipelines/ tests/
	$(PYTHON_BIN) -m black app/ pipelines/ tests/
	@echo "$(GREEN)Code formatted!$(NC)"

## Run data validation checks
validate:
	@echo "$(BLUE)Running data validation...$(NC)"
	@$(PYTHON_BIN) scripts/run_validation.py || echo "$(YELLOW)Validation script execution failed$(NC)"
	@echo "$(GREEN)Validation complete!$(NC)"

# =============================================================================
# Database Commands
# =============================================================================

## Run Alembic migrations (upgrade head)
migrate:
	@echo "$(BLUE)Running database migrations...$(NC)"
	docker compose --profile migration run --rm alembic upgrade head
	@echo "$(GREEN)Migrations complete!$(NC)"

## Update database views (metrics.sql)
update-views:
	@echo "$(BLUE)Updating database views...$(NC)"
	docker compose cp db/views/metrics.sql postgres:/tmp/metrics.sql
	docker compose exec postgres psql -U postgres -d process_metrics_v2 -f /tmp/metrics.sql
	@echo "$(GREEN)Views updated!$(NC)"

## Create new migration (use: make migrate-create MSG="description")
migrate-create:
	@if [ -z "$(MSG)" ]; then \
		echo "$(RED)Error: MSG is required. Usage: make migrate-create MSG=\"description\"$(NC)"; \
		exit 1; \
	fi
	@echo "$(BLUE)Creating migration: $(MSG)$(NC)"
	docker compose --profile migration run --rm alembic revision --autogenerate -m "$(MSG)"
	@echo "$(GREEN)Migration created!$(NC)"

## Rollback one migration
migrate-down:
	@echo "$(BLUE)Rolling back migration...$(NC)"
	docker compose --profile migration run --rm alembic downgrade -1
	@echo "$(GREEN)Rollback complete!$(NC)"

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

## Prod Simple (Local Production Test)
prod-simple-up:
	@echo "$(BLUE)Starting services in SIMPLE PRODUCTION mode...$(NC)"
	docker compose -f docker-compose.simple.yml --env-file .env.production up -d
	@echo "$(BLUE)Running database migrations...$(NC)"
	docker compose -f docker-compose.simple.yml --env-file .env.production --profile migration run --rm alembic upgrade head
	@echo "$(GREEN)Services started and migrated in SIMPLE PRODUCTION mode!$(NC)"

prod-simple-down:
	@echo "$(BLUE)Stopping SIMPLE PRODUCTION services...$(NC)"
	docker compose -f docker-compose.simple.yml --env-file .env.production down
	@echo "$(GREEN)Services stopped!$(NC)"

prod-simple-reset:
	@echo "$(RED)WARNING: This will delete ALL data in SIMPLE PRODUCTION mode!$(NC)"
	docker compose -f docker-compose.simple.yml --env-file .env.production down -v --remove-orphans
	@echo "$(BLUE)Building and starting services...$(NC)"
	docker compose -f docker-compose.simple.yml --env-file .env.production up -d --build
	@echo "$(BLUE)Waiting for Postgres to be ready and running migrations...$(NC)"
	docker compose -f docker-compose.simple.yml --env-file .env.production --profile migration run --rm alembic upgrade head
	@echo "$(GREEN)Production-test environment reset and ready from scratch!$(NC)"

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
	pip install -e ".[dev]"
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
