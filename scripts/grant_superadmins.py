from __future__ import annotations

import argparse
import os
import re
import secrets
import string
import sys
from dataclasses import dataclass

import bcrypt
import requests
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
    if os.getenv("DB_URL_USE_LOCALHOST", "").strip() == "1" and "@postgres:" in db_url:
        db_url = db_url.replace("@postgres:", "@localhost:", 1)
    return db_url


def _resolve_metabase_url() -> str:
    explicit = os.getenv("METABASE_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    return "http://metabase:3000"


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


def _get_metabase_session(url: str, admin_email: str, admin_password: str) -> str:
    resp = requests.post(
        f"{url}/api/session",
        json={"username": admin_email, "password": admin_password},
        timeout=20,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"Metabase auth failed: {resp.status_code} {resp.text[:200]}"
        )
    token = resp.json().get("id")
    if not token:
        raise RuntimeError("Metabase auth failed: no session id")
    return token


def _find_metabase_user(url: str, token: str, email: str) -> dict | None:
    resp = requests.get(
        f"{url}/api/user",
        params={"query": email},
        headers={"X-Metabase-Session": token},
        timeout=20,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"Metabase search failed: {resp.status_code} {resp.text[:200]}"
        )

    users = resp.json()
    if not isinstance(users, list):
        return None
    for user in users:
        if str(user.get("email", "")).lower() == email.lower():
            return user
    return None


def _create_metabase_user(
    url: str, token: str, email: str, display_name: str, password: str
) -> None:
    first_name, last_name = _split_name(display_name)
    resp = requests.post(
        f"{url}/api/user",
        headers={"X-Metabase-Session": token},
        json={
            "email": email,
            "first_name": first_name,
            "last_name": last_name or ".",
            "password": password,
            "is_superuser": True,
        },
        timeout=20,
    )
    if resp.status_code not in {200, 201}:
        raise RuntimeError(
            f"Metabase create failed: {resp.status_code} {resp.text[:200]}"
        )


def _promote_metabase_user(url: str, token: str, user: dict, display_name: str) -> None:
    user_id = user.get("id")
    if not user_id:
        raise RuntimeError("Metabase user payload has no id")
    first_name, last_name = _split_name(display_name)
    payload = {
        "email": user.get("email"),
        "first_name": first_name,
        "last_name": last_name or ".",
        "is_superuser": True,
        "is_active": True,
    }
    resp = requests.put(
        f"{url}/api/user/{user_id}",
        headers={"X-Metabase-Session": token},
        json=payload,
        timeout=20,
    )
    if resp.status_code not in {200, 202}:
        raise RuntimeError(
            f"Metabase promote failed: {resp.status_code} {resp.text[:200]}"
        )


def _ensure_metabase_admin_membership(conn, email: str) -> None:
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


@dataclass
class ResultRow:
    email: str
    platform_status: str
    metabase_status: str


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Grant super-admin access in platform admin + Metabase."
    )
    parser.add_argument("emails", nargs="+", help="Target email list")
    parser.add_argument(
        "--clone-password-from",
        default="admin@example.com",
        help="Copy platform password hash from this user (default: admin@example.com)",
    )
    parser.add_argument(
        "--no-password-overwrite",
        action="store_true",
        help="Do not overwrite existing platform password hashes",
    )
    args = parser.parse_args()

    db_url = _resolve_db_url()
    mb_url = _resolve_metabase_url()
    mb_admin_email = os.getenv("MB_ADMIN_EMAIL", "").strip()
    mb_admin_password = os.getenv("MB_ADMIN_PASSWORD", "").strip()
    if not mb_admin_email or not mb_admin_password:
        raise RuntimeError("MB_ADMIN_EMAIL and MB_ADMIN_PASSWORD must be set")

    engine = create_engine(db_url, future=True)
    overwrite_password_hash = not args.no_password_overwrite
    fallback_hash = bcrypt.hashpw(
        _build_random_password().encode(), bcrypt.gensalt()
    ).decode()
    metabase_initial_password = _build_random_password()
    results: list[ResultRow] = []

    with engine.begin() as conn:
        clone_hash = _fetch_password_hash(conn, args.clone_password_from)
        effective_hash = clone_hash or fallback_hash
        mb_token = _get_metabase_session(mb_url, mb_admin_email, mb_admin_password)

        for email in args.emails:
            display_name = _derive_display_name(email)
            _upsert_platform_user(
                conn,
                email=email,
                display_name=display_name,
                password_hash=effective_hash,
                overwrite_password_hash=overwrite_password_hash,
            )

            existing = _find_metabase_user(mb_url, mb_token, email)
            if existing:
                _promote_metabase_user(mb_url, mb_token, existing, display_name)
                metabase_status = "promoted"
            else:
                _create_metabase_user(
                    mb_url, mb_token, email, display_name, metabase_initial_password
                )
                metabase_status = "created"

            _ensure_metabase_admin_membership(conn, email)
            results.append(
                ResultRow(
                    email=email,
                    platform_status="upserted",
                    metabase_status=metabase_status,
                )
            )

    print("Super-admin access granted:")
    for row in results:
        print(
            f" - {row.email}: platform={row.platform_status}, metabase={row.metabase_status}"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
