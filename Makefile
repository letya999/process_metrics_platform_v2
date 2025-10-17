.PHONY: help lint test docker-build docker-up docker-down ci clean

help:
	@echo "Available targets: help, lint, test, docker-build, docker-up, docker-down, ci, clean"

lint:
	@echo "Running linters..."
	black --check . || (echo "Run 'black .' to format" && exit 1)
	isort --check-only . || (echo "Run 'isort .' to sort imports" && exit 1)
	ruff check . || (echo "Run 'ruff --fix .' to fix lint issues" && exit 1)

test:
	@echo "Running tests..."
	pytest --cov=.

docker-build:
	@echo "Building docker images for services (uses DOCKER_BUILDKIT=1)"
	export DOCKER_BUILDKIT=1 && docker build -t auth_service:local services/auth_service

docker-up:
	@echo "Starting docker-compose stack"
	docker-compose up -d

docker-down:
	@echo "Stopping docker-compose stack"
	docker-compose down

ci: lint test docker-build
	@echo "CI tasks completed"

clean:
	@echo "Cleaning python caches and build artifacts"
	rm -rf .pytest_cache .venv build dist __pycache__
