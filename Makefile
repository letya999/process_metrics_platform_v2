.PHONY: help lint test docker-build docker-up docker-down ci clean migrate up-core gen-env setup

DOCKER_BUILDKIT ?= 1
export DOCKER_BUILDKIT

# Detect OS for cross-platform commands
ifeq ($(OS),Windows_NT)
    SLEEP_CMD = powershell -NoProfile -Command "Start-Sleep -Seconds 15"
    RM_CMD = del /q /s
else
    SLEEP_CMD = sleep 15
    RM_CMD = rm -rf
endif

help:
	@echo "Available targets:"
	@echo "  help          - Show this help message"
	@echo "  lint          - Run code linting"
	@echo "  test          - Run tests"
	@echo "  docker-build  - Build docker images"
	@echo "  docker-up     - Start all services"
	@echo "  docker-down   - Stop all services"
	@echo "  up-core       - Start core services only"
	@echo "  setup         - Full setup: check DB + migrate if needed"
	@echo "  gen-env       - Generate strong passwords for .env"
	@echo "  clean         - Clean build artifacts"

lint:
	@echo "Running linters..."
	black --check . || (echo "Run 'black .' to format" && exit 1)
	isort --check-only . || (echo "Run 'isort .' to sort imports" && exit 1)
	ruff check . || (echo "Run 'ruff --fix .' to fix lint issues" && exit 1)

test:
	@echo "Running tests..."
	pdm run pytest

gen-env:
	@echo "Generating strong passwords for .env:"
	python common/scripts/generate_env_passwords.py

docker-build:
	@echo "Building docker images (DOCKER_BUILDKIT=$(DOCKER_BUILDKIT))"
	docker build -t auth_service:local services/auth_service
	@echo "Exporting dlt_jira_loader requirements via PDM"
	cd services/dlt_jira_loader && pdm export --prod --without-hashes -o requirements.txt
	@echo "Building dlt_jira_loader image"
	docker build -t dlt_jira_loader:local services/dlt_jira_loader

docker-up:
	@echo "Starting all services"
	docker-compose up -d

docker-down:
	@echo "Stopping all services"
	docker-compose down

up-core:
	@echo "Starting core services: postgres, redis, prefect"
	docker-compose up -d postgres redis prefect-server prefect-worker dlt_jira_worker

deploy-jira:
	@echo "Registering Prefect deployments for Jira sync"
	cd services/dlt_jira_loader && python deployments/deploy.py

reset-db:
	@echo "=== DESTROYING DATABASE AND RECREATING ==="
	docker-compose down
	docker volume rm process_metrics_platform_v2_postgres_data || true
	docker-compose up -d postgres redis
	@echo "Waiting for postgres to initialize..."
	@$(SLEEP_CMD)
	@$(MAKE) debug-db

# Check what's in the database
debug-db:
	@echo "=== CHECKING DATABASE STATE ==="
	@docker-compose exec postgres psql -U postgres -d process_metrics_v2 -c "\dn" || echo "Failed to connect"
	@docker-compose exec postgres psql -U postgres -d process_metrics_v2 -c "SELECT schemaname FROM pg_tables WHERE schemaname = 'platform';" || echo "Failed to query"

setup: up-core
	@echo "Setting up database and migrations..."
	@$(MAKE) debug-db
	@docker-compose run --rm alembic sh -c "\
		apt-get update -qq && apt-get install -y -qq postgresql-client && \
		pip install -q alembic asyncpg psycopg2-binary && \
		echo 'Waiting for postgres...' && \
		until pg_isready -h postgres -U postgres -d process_metrics_v2; do sleep 2; done && \
		echo 'Running migrations...' && \
		alembic -c db/migrations/alembic.ini upgrade head"
	@echo "Setup complete!"

ci: lint test docker-build
	@echo "CI pipeline completed"

clean:
	@echo "Cleaning build artifacts"
	$(RM_CMD) .pytest_cache .venv build dist __pycache__

force-reset:
	@echo "=== FORCE RESET DATABASE (REMOVES ALL DATA) ==="
	@echo "Stopping all containers..."
	docker-compose down -v
	@echo "Removing ALL volumes..."
	docker volume prune -f
	@echo "Removing specific postgres volume..."
	- docker volume rm process_metrics_platform_v2_postgres_data
	@echo "Starting fresh postgres..."
	docker-compose up -d postgres
	@echo "Waiting 30 seconds for initialization..."
	@powershell -NoProfile -Command "Start-Sleep -Seconds 30" || sleep 30
	@echo "Checking database state..."
	@$(MAKE) debug-db
