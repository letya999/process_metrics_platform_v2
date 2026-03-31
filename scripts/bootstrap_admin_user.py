"""Create or update admin user from environment variables.

Required env vars:
- ADMIN_BOOTSTRAP_EMAIL
- ADMIN_BOOTSTRAP_PASSWORD

Optional env vars:
- ADMIN_BOOTSTRAP_DISPLAY_NAME (default: Admin)
- DATABASE_URL or ALEMBIC_SQLALCHEMY_URL
"""

from __future__ import annotations

import os
import sys

import bcrypt
from sqlalchemy import create_engine, text


def _get_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def main() -> int:
    db_url = (
        os.getenv("DATABASE_URL", "").strip()
        or os.getenv("ALEMBIC_SQLALCHEMY_URL", "").strip()
    )
    if not db_url:
        raise RuntimeError("DATABASE_URL or ALEMBIC_SQLALCHEMY_URL must be set")

    email = _get_required_env("ADMIN_BOOTSTRAP_EMAIL")
    password = _get_required_env("ADMIN_BOOTSTRAP_PASSWORD")
    display_name = os.getenv("ADMIN_BOOTSTRAP_DISPLAY_NAME", "Admin").strip() or "Admin"
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    engine = create_engine(db_url, future=True)
    upsert_sql = text(
        """
        INSERT INTO platform.users (email, password_hash, display_name, is_active, is_admin)
        VALUES (:email, :password_hash, :display_name, true, true)
        ON CONFLICT (email) DO UPDATE
        SET
            password_hash = EXCLUDED.password_hash,
            display_name = EXCLUDED.display_name,
            is_active = true,
            is_admin = true,
            updated_at = now()
        """
    )

    with engine.begin() as conn:
        conn.execute(
            upsert_sql,
            {
                "email": email,
                "password_hash": password_hash,
                "display_name": display_name,
            },
        )

    print(f"Admin user is ready: {email}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
