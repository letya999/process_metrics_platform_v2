# Contributing to Process Metrics Platform

Thank you for your interest in contributing! This document provides guidelines for setting up your environment and submitting changes.

## Prerequisites

- Python 3.11+
- Docker & Docker Compose
- `make` (optional, for convenience)

## Local Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/your-org/process-metrics-platform-v2.git
   cd process-metrics-platform-v2
   ```

2. **Setup environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your local settings if needed
   ```

3. **Start the local stack**:
   ```bash
   docker compose up -d
   ```

4. **Run migrations**:
   ```bash
   # Using the migration profile
   docker compose run --rm alembic
   ```

5. **Install local development dependencies**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # .venv\Scripts\Activate on Windows
   pip install -e ".[dev]"
   ```

## Development Workflow

### Running Tests

We use `pytest` for testing. Ensure your changes don't break existing functionality.

```bash
make test
# OR
pytest
```

### Code Style

We use `ruff` for linting and formatting.

```bash
make lint
# OR
ruff check .
ruff format .
```

### Branch Naming

Use descriptive branch names with the following prefixes:
- `feature/` for new features
- `bugfix/` for bug fixes
- `hotfix/` for urgent production fixes
- `docs/` for documentation changes

### Commit Messages

We follow [Conventional Commits](https://www.conventionalcommits.org/):
- `feat: ...`
- `fix: ...`
- `refactor: ...`
- `docs: ...`
- `test: ...`
- `chore: ...`

## Pull Request Process

1. Fork the repository.
2. Create a branch from `main`.
3. Make your changes and ensure all tests pass and linting is clean.
4. Submit a Pull Request to the `main` branch.
5. Provide a clear description of the changes and the problem they solve.

---
*Note: We prioritize clean, well-tested code that adheres to the existing architectural patterns.*
