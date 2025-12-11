"""Integration tests for database migrations.

These tests verify that Alembic migrations can run successfully.
Requires a running PostgreSQL database (configured via DATABASE_URL).
"""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


def get_alembic_config() -> Config:
    """Get Alembic configuration."""
    project_root = Path(__file__).parent.parent.parent
    alembic_cfg = Config(str(project_root / "db" / "migrations" / "alembic.ini"))
    alembic_cfg.set_main_option(
        "script_location", str(project_root / "db" / "migrations")
    )
    return alembic_cfg


@pytest.fixture
def database_url() -> str:
    """Get database URL from environment."""
    url = os.getenv("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set, skipping migration tests")
    return url


@pytest.fixture
def alembic_config(database_url: str) -> Config:
    """Get Alembic config with database URL."""
    cfg = get_alembic_config()
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


@pytest.fixture
def clean_database(database_url: str):
    """Clean database before/after test by dropping all schemas."""
    engine = create_engine(database_url)

    def drop_schemas():
        with engine.connect() as conn:
            # Drop all custom schemas
            schemas = ["platform", "raw_jira", "clean_jira", "metrics", "bi_analytics"]
            for schema in schemas:
                conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            # Drop alembic version table
            conn.execute(text("DROP TABLE IF EXISTS alembic_version CASCADE"))
            conn.commit()

    drop_schemas()
    yield
    drop_schemas()


class TestMigrationStructure:
    """Test migration file structure without running migrations."""

    def test_migrations_directory_exists(self):
        """Verify migrations directory structure exists."""
        project_root = Path(__file__).parent.parent.parent
        migrations_dir = project_root / "db" / "migrations"

        assert migrations_dir.exists(), "db/migrations directory should exist"
        assert (migrations_dir / "versions").exists(), "versions directory should exist"
        assert (migrations_dir / "env.py").exists(), "env.py should exist"
        assert (migrations_dir / "alembic.ini").exists(), "alembic.ini should exist"

    def test_migration_files_exist(self):
        """Verify all expected migration files exist."""
        project_root = Path(__file__).parent.parent.parent
        versions_dir = project_root / "db" / "migrations" / "versions"

        # Expected migration files
        expected_migrations = [
            "0001_initial.py",
            "0002_add_integration_sync_checkpoints.py",
            "0003_update_pipeline_runs_jira_metadata.py",
            "0004_add_metrics_schema.py",
        ]

        for migration_file in expected_migrations:
            assert (
                versions_dir / migration_file
            ).exists(), f"Migration {migration_file} should exist"

    def test_sql_schema_files_exist(self):
        """Verify all SQL schema files exist."""
        project_root = Path(__file__).parent.parent.parent
        db_dir = project_root / "db"

        expected_files = [
            "init/01_create_schemas.sql",
            "schemas/platform_schema.sql",
            "schemas/clean_jira_schema.sql",
            "schemas/bi_analytics_schema.sql",
            "views/metrics.sql",
        ]

        for sql_file in expected_files:
            assert (db_dir / sql_file).exists(), f"SQL file {sql_file} should exist"

    def test_metrics_views_contains_required_views(self):
        """Verify metrics.sql contains all required materialized views."""
        project_root = Path(__file__).parent.parent.parent
        metrics_sql = project_root / "db" / "views" / "metrics.sql"

        content = metrics_sql.read_text()

        # Check for required materialized views
        assert "mv_lead_time" in content, "mv_lead_time view should be defined"
        assert "mv_velocity" in content, "mv_velocity view should be defined"
        assert "mv_throughput" in content, "mv_throughput view should be defined"
        assert (
            "refresh_all_views" in content
        ), "refresh_all_views function should be defined"


class TestMigrationRevisions:
    """Test migration revision chain."""

    def test_revision_chain_is_valid(self):
        """Verify migration revision chain is continuous."""
        project_root = Path(__file__).parent.parent.parent
        versions_dir = project_root / "db" / "migrations" / "versions"

        # Read revision info from each file
        revisions = {}
        for py_file in versions_dir.glob("*.py"):
            if py_file.name == "__pycache__":
                continue
            content = py_file.read_text()

            # Extract revision and down_revision
            for line in content.splitlines():
                if line.startswith("revision = "):
                    rev = line.split("=")[1].strip().strip('"')
                    revisions[py_file.name] = {"revision": rev}
                if line.startswith("down_revision = "):
                    down = line.split("=")[1].strip().strip('"')
                    if down == "None":
                        down = None
                    revisions[py_file.name]["down_revision"] = down

        # Verify chain: 0001 -> 0002 -> 0003 -> 0004
        assert revisions["0001_initial.py"]["down_revision"] is None
        assert (
            revisions["0002_add_integration_sync_checkpoints.py"]["down_revision"]
            == "0001_initial"
        )
        assert (
            revisions["0003_update_pipeline_runs_jira_metadata.py"]["down_revision"]
            == "0002_sync_checkpoints"
        )
        assert (
            revisions["0004_add_metrics_schema.py"]["down_revision"]
            == "0003_pipeline_runs_jira"
        )


@pytest.mark.integration
class TestMigrationExecution:
    """Test actual migration execution (requires database)."""

    def test_migrate_up_to_head(
        self, alembic_config: Config, clean_database, database_url: str
    ):
        """Test upgrading to latest migration."""
        # Run migrations up to head
        command.upgrade(alembic_config, "head")

        # Verify alembic version is at head
        engine = create_engine(database_url)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version"))
            version = result.scalar()
            assert (
                version == "0004_metrics_schema"
            ), f"Expected head version, got {version}"

    def test_migrate_down_to_base(
        self, alembic_config: Config, clean_database, database_url: str
    ):
        """Test downgrading all migrations."""
        # First upgrade to head
        command.upgrade(alembic_config, "head")

        # Then downgrade to base
        command.downgrade(alembic_config, "base")

        # Verify no version in alembic_version
        engine = create_engine(database_url)
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
                    "WHERE table_name = 'alembic_version')"
                )
            )
            exists = result.scalar()
            if exists:
                result = conn.execute(text("SELECT version_num FROM alembic_version"))
                version = result.scalar()
                assert (
                    version is None
                ), f"Expected no version after downgrade, got {version}"

    def test_migrate_step_by_step(
        self, alembic_config: Config, clean_database, database_url: str
    ):
        """Test upgrading one step at a time."""
        engine = create_engine(database_url)

        # Step 1: Initial
        command.upgrade(alembic_config, "0001_initial")
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version"))
            assert result.scalar() == "0001_initial"

        # Step 2: Sync checkpoints
        command.upgrade(alembic_config, "0002_sync_checkpoints")
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version"))
            assert result.scalar() == "0002_sync_checkpoints"

            # Verify table was created
            result = conn.execute(
                text(
                    "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'platform' "
                    "AND table_name = 'integration_sync_checkpoints')"
                )
            )
            assert result.scalar(), "integration_sync_checkpoints table should exist"

        # Step 3: Pipeline runs jira
        command.upgrade(alembic_config, "0003_pipeline_runs_jira")
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version"))
            assert result.scalar() == "0003_pipeline_runs_jira"

        # Step 4: Metrics schema
        command.upgrade(alembic_config, "0004_metrics_schema")
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version"))
            assert result.scalar() == "0004_metrics_schema"

            # Verify metrics schema and views were created
            result = conn.execute(
                text(
                    "SELECT EXISTS(SELECT 1 FROM information_schema.schemata "
                    "WHERE schema_name = 'metrics')"
                )
            )
            assert result.scalar(), "metrics schema should exist"

            # Verify materialized views exist
            result = conn.execute(
                text("SELECT COUNT(*) FROM pg_matviews " "WHERE schemaname = 'metrics'")
            )
            count = result.scalar()
            assert count == 3, f"Expected 3 materialized views, got {count}"
