from __future__ import annotations

import argparse
import os
import re
import secrets
import string
import sys

import bcrypt
from sqlalchemy import create_engine, text


def _derive_display_name(email: str) -> str:
    local_part = email.split("@")[0]
    name = re.sub(r"[._-]", " ", local_part)
    return name.strip().title() or email


def _split_name(display_name: str) -> tuple[str, str]:
    parts = display_name.split()
    if len(parts) >= 2:
        return parts[0], " ".join(parts[1:])
    return display_name, "."


def _build_random_password(length: int = 24) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _resolve_db_url() -> str:
    db_url = (
        os.getenv("DATABASE_URL", "").strip()
        or os.getenv("ALEMBIC_SQLALCHEMY_URL", "").strip()
    )
    if not db_url:
        raise RuntimeError("DATABASE_URL or ALEMBIC_SQLALCHEMY_URL must be set")

    # Allows running from host machine when env uses docker DNS.
    if "@postgres:" in db_url:
        db_url = db_url.replace("@postgres:", "@localhost:", 1)
    return db_url


def _fetch_password_hash(conn, source_email: str) -> str | None:
    row = conn.execute(
        text(
            """
            SELECT password_hash
            FROM platform.users
            WHERE email = :email
            """
        ),
        {"email": source_email},
    ).first()
    if not row:
        return None
    return row[0]


def _upsert_platform_user(
    conn,
    email: str,
    display_name: str,
    password_hash: str,
    overwrite_password_hash: bool,
) -> None:
    conn.execute(
        text(
            """
            INSERT INTO platform.users (
                email,
                password_hash,
                display_name,
                is_active,
                is_admin
            )
            VALUES (
                :email,
                :password_hash,
                :display_name,
                true,
                true
            )
            ON CONFLICT (email) DO UPDATE
            SET
                password_hash = CASE
                    WHEN :overwrite_password_hash
                    THEN EXCLUDED.password_hash
                    ELSE platform.users.password_hash
                END,
                display_name = EXCLUDED.display_name,
                is_active = true,
                is_admin = true,
                updated_at = now()
            """
        ),
        {
            "email": email,
            "password_hash": password_hash,
            "display_name": display_name,
            "overwrite_password_hash": overwrite_password_hash,
        },
    )


def _upsert_metabase_superuser(
    conn,
    email: str,
    display_name: str,
    password_hash: str,
    overwrite_password_hash: bool,
) -> None:
    first_name, last_name = _split_name(display_name)
    conn.execute(
        text(
            """
            INSERT INTO core_user (
                email,
                first_name,
                last_name,
                is_active,
                is_superuser,
                password
            )
            VALUES (
                :email,
                :first_name,
                :last_name,
                true,
                true,
                :password_hash
            )
            ON CONFLICT (email) DO UPDATE
            SET
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                is_active = true,
                is_superuser = true,
                password = CASE
                    WHEN :overwrite_password_hash
                    THEN EXCLUDED.password
                    ELSE core_user.password
                END
            """
        ),
        {
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "password_hash": password_hash,
            "overwrite_password_hash": overwrite_password_hash,
        },
    )

    conn.execute(
        text(
            """
            INSERT INTO permissions_group_membership (user_id, group_id)
            SELECT cu.id, pg.id
            FROM core_user cu
            JOIN permissions_group pg ON pg.name = 'Administrators'
            WHERE cu.email = :email
            ON CONFLICT DO NOTHING
            """
        ),
        {"email": email},
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Grant super-admin access in platform admin + Metabase."
    )
    parser.add_argument("emails", nargs="+", help="Target email list")
    parser.add_argument(
        "--clone-password-from",
        default="admin@example.com",
        help="Copy password hash from this platform user (default: admin@example.com)",
    )
    parser.add_argument(
        "--no-password-overwrite",
        action="store_true",
        help="Do not overwrite existing password hashes for existing users",
    )
    args = parser.parse_args()

    db_url = _resolve_db_url()
    engine = create_engine(db_url, future=True)

    overwrite_password_hash = not args.no_password_overwrite
    fallback_hash = bcrypt.hashpw(
        _build_random_password().encode(), bcrypt.gensalt()
    ).decode()

    with engine.begin() as conn:
        clone_hash = _fetch_password_hash(conn, args.clone_password_from)
        effective_hash = clone_hash or fallback_hash

        for email in args.emails:
            display_name = _derive_display_name(email)
            _upsert_platform_user(
                conn,
                email=email,
                display_name=display_name,
                password_hash=effective_hash,
                overwrite_password_hash=overwrite_password_hash,
            )
            _upsert_metabase_superuser(
                conn,
                email=email,
                display_name=display_name,
                password_hash=effective_hash,
                overwrite_password_hash=overwrite_password_hash,
            )

    source_info = (
        f"password hash source: {args.clone_password_from}"
        if clone_hash
        else "password hash source: generated fallback"
    )
    print("Super-admin access granted for:")
    for email in args.emails:
        print(f" - {email}")
    print(source_info)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
