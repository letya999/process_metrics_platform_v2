from __future__ import annotations

import argparse
import os
import re
import secrets
import string
import sys
from pathlib import Path

import bcrypt
import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Load .env from project root
ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")

ALPHABET = string.ascii_letters + string.digits + "!@#$%^&*"


def generate_password(length: int = 16) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def derive_display_name(email: str) -> str:
    local_part = email.split("@")[0]
    # Replace dots, underscores, hyphens with space
    name = re.sub(r"[._-]", " ", local_part)
    return name.strip().title()


def split_display_name(display_name: str) -> tuple[str, str]:
    parts = display_name.split()
    if len(parts) >= 2:
        return parts[0], " ".join(parts[1:])
    return display_name, "."  # Use dot for last_name if single-word display name


def provision_platform(
    engine, email: str, password: str, display_name: str, is_admin: bool
) -> str:
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    upsert_sql = text(
        """
        INSERT INTO platform.users (email, password_hash, display_name, is_active, is_admin)
        VALUES (:email, :password_hash, :display_name, true, :is_admin)
        ON CONFLICT (email) DO UPDATE
        SET
            password_hash = EXCLUDED.password_hash,
            display_name = EXCLUDED.display_name,
            is_active = true,
            is_admin = CASE WHEN :force_admin THEN true ELSE platform.users.is_admin END,
            updated_at = now()
        RETURNING (xmax = 0) AS is_insert
        """
    )
    try:
        with engine.begin() as conn:
            res = conn.execute(
                upsert_sql,
                {
                    "email": email,
                    "password_hash": password_hash,
                    "display_name": display_name,
                    "is_admin": is_admin,
                    "force_admin": is_admin,
                },
            )
            row = res.fetchone()
            if row and row[0]:  # is_insert is True
                return "created"
            return "updated"
    except Exception as e:
        return f"ERROR: {e}"


def get_metabase_session(url: str, email: str, password: str) -> str | None:
    try:
        resp = requests.post(
            f"{url.rstrip('/')}/api/session",
            json={"username": email, "password": password},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json().get("id")
    except Exception:  # noqa: S110
        pass
    return None


def provision_metabase(
    url: str,
    session_token: str,
    email: str,
    password: str,
    display_name: str,
    is_admin: bool,
) -> str:
    headers = {"X-Metabase-Session": session_token}
    first_name, last_name = split_display_name(display_name)

    # 1. Check if user exists
    try:
        search_resp = requests.get(
            f"{url.rstrip('/')}/api/user",
            params={"query": email},
            headers=headers,
            timeout=10,
        )
        if search_resp.status_code == 200:
            users = search_resp.json()
            if isinstance(users, list):
                for u in users:
                    if u.get("email") == email:
                        return "already exists"
    except Exception as e:
        return f"ERROR: check failed ({e})"

    # 2. Create user
    try:
        create_resp = requests.post(
            f"{url.rstrip('/')}/api/user",
            json={
                "email": email,
                "first_name": first_name,
                "last_name": last_name
                or " ",  # Metabase might require last_name non-empty
                "password": password,
                "is_superuser": is_admin,
            },
            headers=headers,
            timeout=10,
        )
        if create_resp.status_code == 200:
            return "created"
        if create_resp.status_code == 400:
            body = create_resp.text
            if "Email address already in use" in body:
                return "already exists"
            return f"ERROR: {body[:50]}"
        return f"ERROR: status {create_resp.status_code}"
    except Exception as e:
        return f"ERROR: {e}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Provision users in Platform DB and Metabase"
    )
    parser.add_argument("emails", nargs="+", help="Email addresses to provision")
    parser.add_argument(
        "--admin", action="store_true", help="Set is_admin/is_superuser=true"
    )
    parser.add_argument("--no-metabase", action="store_true", help="Skip Metabase step")
    parser.add_argument(
        "--no-platform", action="store_true", help="Skip Platform DB step"
    )
    args = parser.parse_args()

    db_url = (
        os.getenv("DATABASE_URL", "").strip()
        or os.getenv("ALEMBIC_SQLALCHEMY_URL", "").strip()
    )

    mb_url = os.getenv("METABASE_URL", "http://localhost:3001").strip()
    mb_admin_email = os.getenv("MB_ADMIN_EMAIL", "").strip()
    mb_admin_password = os.getenv("MB_ADMIN_PASSWORD", "").strip()

    if not args.no_platform and not db_url:
        print(
            "ERROR: DATABASE_URL or ALEMBIC_SQLALCHEMY_URL must be set", file=sys.stderr
        )
        return 1

    # When running locally (outside Docker), replace docker-internal hostname with localhost
    if db_url and "@postgres:" in db_url:
        db_url = db_url.replace("@postgres:", "@localhost:", 1)

    engine = None
    if not args.no_platform:
        engine = create_engine(db_url, future=True)

    mb_session = None
    if not args.no_metabase:
        if not mb_admin_email or not mb_admin_password:
            print("WARNING: MB_ADMIN_EMAIL/PASSWORD not set. Metabase steps will fail.")
        else:
            mb_session = get_metabase_session(mb_url, mb_admin_email, mb_admin_password)
            if not mb_session:
                print("WARNING: Metabase authentication failed.")

    results = []
    any_error = False

    for email in args.emails:
        password = generate_password()
        display_name = derive_display_name(email)

        platform_status = "skipped"
        if not args.no_platform:
            platform_status = provision_platform(
                engine, email, password, display_name, args.admin
            )
            if platform_status.startswith("ERROR"):
                any_error = True

        metabase_status = "skipped"
        if not args.no_metabase:
            if mb_session:
                metabase_status = provision_metabase(
                    mb_url, mb_session, email, password, display_name, args.admin
                )
                if metabase_status.startswith("ERROR"):
                    any_error = True
            else:
                metabase_status = "ERROR: auth failed"
                any_error = True

        results.append(
            {
                "email": email,
                "password": password,
                "platform": platform_status,
                "metabase": metabase_status,
            }
        )

    # Print results table
    print(
        "\n+------------------------------------------+------------------+------------+------------+"
    )
    print(
        "| Email                                    | Password         | Platform   | Metabase   |"
    )
    print(
        "+------------------------------------------+------------------+------------+------------+"
    )
    for r in results:
        print(
            f"| {r['email']:40} | {r['password']:16} | {r['platform']:10} | {r['metabase']:10} |"
        )
    print(
        "+------------------------------------------+------------------+------------+------------+"
    )

    return 1 if any_error else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:
        print(f"FATAL ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
