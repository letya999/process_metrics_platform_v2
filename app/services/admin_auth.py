"""Admin auth helpers: password verification and stateless signed sessions."""

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import bcrypt

DEFAULT_ADMIN_TOKEN_TTL_MINUTES = 480


@dataclass
class AdminSession:
    user_id: str
    email: str
    display_name: str
    is_admin: bool
    expires_at: datetime


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(f"{data}{padding}".encode("ascii"))


def _get_signing_secret() -> str:
    return (
        os.getenv("ADMIN_AUTH_SECRET")
        or os.getenv("SECRET_KEY")
        or "dev-insecure-secret-change-me"
    )


def _sign(data: str) -> str:
    digest = hmac.new(
        _get_signing_secret().encode("utf-8"),
        data.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return _b64url_encode(digest)


def _serialize(session: AdminSession) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": session.user_id,
        "email": session.email,
        "name": session.display_name,
        "is_admin": session.is_admin,
        "exp": int(session.expires_at.timestamp()),
    }
    encoded_header = _b64url_encode(
        json.dumps(header, separators=(",", ":")).encode("utf-8")
    )
    encoded_payload = _b64url_encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    )
    signing_input = f"{encoded_header}.{encoded_payload}"
    signature = _sign(signing_input)
    return f"{signing_input}.{signature}"


def _deserialize(token: str) -> AdminSession | None:
    parts = token.split(".")
    if len(parts) != 3:
        return None

    encoded_header, encoded_payload, signature = parts
    signing_input = f"{encoded_header}.{encoded_payload}"
    expected_signature = _sign(signing_input)
    if not hmac.compare_digest(signature, expected_signature):
        return None

    try:
        header = json.loads(_b64url_decode(encoded_header))
        payload = json.loads(_b64url_decode(encoded_payload))
    except (ValueError, json.JSONDecodeError):
        return None

    if header.get("alg") != "HS256" or header.get("typ") != "JWT":
        return None

    try:
        expires_at = datetime.fromtimestamp(int(payload["exp"]), tz=UTC)
        if expires_at < datetime.now(UTC):
            return None

        return AdminSession(
            user_id=str(payload["sub"]),
            email=str(payload["email"]),
            display_name=str(payload.get("name", "")),
            is_admin=bool(payload.get("is_admin", False)),
            expires_at=expires_at,
        )
    except (KeyError, TypeError, ValueError, OSError):
        return None


def create_access_token(
    session: AdminSession, ttl_minutes: int = DEFAULT_ADMIN_TOKEN_TTL_MINUTES
) -> tuple[str, datetime]:
    expires_at = datetime.now(UTC) + timedelta(minutes=ttl_minutes)
    token = _serialize(
        AdminSession(
            user_id=session.user_id,
            email=session.email,
            display_name=session.display_name,
            is_admin=session.is_admin,
            expires_at=expires_at,
        )
    )
    return token, expires_at


def create_token(
    ttl_minutes: int = DEFAULT_ADMIN_TOKEN_TTL_MINUTES,
) -> tuple[str, datetime]:
    """Backward-compatible wrapper for old tests/callers."""
    session = AdminSession(
        user_id="",
        email="",
        display_name="",
        is_admin=False,
        expires_at=datetime.now(UTC),
    )
    return create_access_token(session, ttl_minutes=ttl_minutes)


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, stored: str) -> tuple[bool, bool]:
    """
    Returns (is_valid, needs_rehash).
    needs_rehash is True when the stored value is still plaintext.
    """
    is_bcrypt = stored.startswith(("$2b$", "$2a$", "$2y$"))
    if is_bcrypt:
        valid = bcrypt.checkpw(plain.encode(), stored.encode())
        return valid, False
    # Legacy plaintext path - constant-time compare to avoid timing attacks.
    valid = hmac.compare_digest(plain, stored)
    return valid, valid


def save_session(token: str, session: AdminSession) -> None:
    """No-op for stateless token mode, kept for backward compatibility."""
    _ = (token, session)


def get_session(token: str) -> AdminSession | None:
    return _deserialize(token)


def revoke_token(token: str) -> None:
    """Stateless tokens cannot be server-revoked without shared store."""
    _ = token


def parse_bearer_token(auth_header: str | None) -> str | None:
    if not auth_header:
        return None
    prefix = "Bearer "
    if not auth_header.startswith(prefix):
        return None
    token = auth_header[len(prefix) :].strip()
    return token or None
