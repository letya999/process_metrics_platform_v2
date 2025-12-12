import importlib
import os
import pkgutil
import sys
from logging.config import fileConfig
from typing import Optional

from alembic import context
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import Connection

# This is the Alembic Config object.
# It provides access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add project path (robust for environments where alembic.Config lacks config_file_path)
if getattr(config, "config_file_name", None):
    config_dir = os.path.dirname(os.path.abspath(config.config_file_name))
else:
    # fallback to current working directory when running inside minimal containers
    config_dir = os.getcwd()

sys.path.append(os.path.abspath(os.path.join(config_dir, "..", "..")))


def _collect_target_metadata() -> Optional[object]:
    """Attempt to auto-discover SQLAlchemy MetaData from service model packages.

    Strategy:
    - Scan the `services/` package for subpackages.
    - For each, try to import `services.<svc>.app.models.orm`.
    - If module exposes `metadata`, return it.
      If it exposes `Base`, return `Base.metadata`.
    - If multiple metadata objects are found, log a warning
      and return None (developer should set explicit metadata).
    """
    found = []
    services_pkg = os.path.join(
        os.path.dirname(os.path.abspath(config_dir)),
        "services",
    )
    if not os.path.isdir(services_pkg):
        return None

    for finder, name, ispkg in pkgutil.iter_modules([services_pkg]):
        module_name = f"services.{name}.app.models.orm"
        try:
            mod = importlib.import_module(module_name)
        except Exception:
            continue
        if hasattr(mod, "metadata"):
            found.append(getattr(mod, "metadata"))
        elif hasattr(mod, "Base"):
            base = getattr(mod, "Base")
            if hasattr(base, "metadata"):
                found.append(base.metadata)

    if len(found) == 1:
        return found[0]
    if len(found) > 1:
        # Too many metadata sources; prefer explicit configuration
        msg = (
            "alembic: multiple metadata objects discovered; "
            "set target_metadata explicitly"
        )
        print(msg, file=sys.stderr)
        return None
    return None


# Auto-discover metadata for autogenerate when possible
target_metadata = _collect_target_metadata()


def _resolve_database_url() -> str:
    """Resolve SQLAlchemy URL in priority order without hardcoding secrets.

    Priority:
    1) ALEMBIC_SQLALCHEMY_URL env var (explicit for Alembic)
    2) DATABASE_URL env var (shared project convention)
    3) sqlalchemy.url from alembic.ini
    """
    env_url = os.getenv("ALEMBIC_SQLALCHEMY_URL") or os.getenv("DATABASE_URL")
    if env_url:
        return env_url
    return config.get_main_option("sqlalchemy.url")


def run_migrations_offline() -> None:
    url = _resolve_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    sections = config.get_section(config.config_ini_section)
    configuration = {
        **sections,
        "sqlalchemy.url": _resolve_database_url(),
    }

    connectable = create_engine(
        configuration["sqlalchemy.url"],
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:  # type: Connection
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
