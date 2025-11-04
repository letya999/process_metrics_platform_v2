"""Utilities for resolving runtime configuration."""
# ruff: noqa: E501
import os
from types import SimpleNamespace


def get_settings():
    """Return settings object.

    Behavior:
    - In production/runtime, require `DATABASE_URL` to be set and use it.
    - For tests, allow `TEST_DATABASE_URL` to provide an override.
    - If neither is set, raise an error to avoid silently using bad defaults.
    """
    db_url = os.getenv("DATABASE_URL") or os.getenv("TEST_DATABASE_URL")
    if not db_url:
        raise RuntimeError(
            "DATABASE_URL environment variable is required. For tests set TEST_DATABASE_URL."
        )
    return SimpleNamespace(database_url=db_url)
