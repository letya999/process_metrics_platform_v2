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
	@echo ""
	@echo "$(GREEN)Development:$(NC)"
	@echo "  make install         - Install Python dependencies"
	@echo "  make clean           - Clean build artifacts"

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

## Run tests with coverage
test:
	@echo "$(BLUE)Running tests...$(NC)"
	python -m pytest tests/ -v --cov=app --cov=pipelines --cov-report=term-missing
	@echo "$(GREEN)Tests passed!$(NC)"

## Check code style with ruff and black
lint:
	@echo "$(BLUE)Checking code style...$(NC)"
	ruff check app/ pipelines/ tests/
	black --check app/ pipelines/ tests/
	@echo "$(GREEN)Linting passed!$(NC)"

## Auto-format code with ruff and black
format:
	@echo "$(BLUE)Formatting code...$(NC)"
	ruff check --fix app/ pipelines/ tests/
	black app/ pipelines/ tests/
	@echo "$(GREEN)Code formatted!$(NC)"

## Run data validation checks
validate:
	@echo "$(BLUE)Running data validation...$(NC)"
	@if [ -f tests/validation/test_data_integrity.py ]; then \
		pytest tests/validation/ -v; \
	else \
		echo "$(YELLOW)No validation tests found (tests/validation/)$(NC)"; \
	fi
	@echo "$(GREEN)Validation complete!$(NC)"

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

## View service logs (follow mode)
docker-logs:
	docker compose logs -f

## Stop services and remove volumes (DESTRUCTIVE)
docker-reset:
	@echo "$(RED)WARNING: This will delete all data!$(NC)"
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ]
	docker compose down -v
	@echo "$(GREEN)Reset complete!$(NC)"

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
	rm -rf .pytest_cache .coverage htmlcov
	rm -rf __pycache__ */__pycache__ */*/__pycache__
	rm -rf .ruff_cache .mypy_cache
	rm -rf build dist *.egg-info
	rm -rf .dagster
	@echo "$(GREEN)Clean complete!$(NC)"

## Run Dagster locally (for development without Docker)
dagster-dev:
	@echo "$(BLUE)Starting Dagster dev server...$(NC)"
	dagster dev -m pipelines.definitions

## Run FastAPI locally (for development without Docker)
api-dev:
	@echo "$(BLUE)Starting FastAPI dev server...$(NC)"
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
