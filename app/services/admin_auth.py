"""Admin auth helpers: password verification and stateless signed sessions."""

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import bcrypt

DEFAULT_ADMIN_TOKEN_TTL_MINUTES = 120


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
    secret = os.getenv("ADMIN_AUTH_SECRET") or os.getenv("SECRET_KEY")
    if not secret:
        raise RuntimeError("ADMIN_AUTH_SECRET or SECRET_KEY must be set")
    return secret


def _get_ttl_minutes(default: int = DEFAULT_ADMIN_TOKEN_TTL_MINUTES) -> int:
    raw = os.getenv("ADMIN_AUTH_TTL_MINUTES")
    if raw is None:
        return default
    try:
        ttl = int(raw)
    except ValueError:
        return default
    return max(5, min(ttl, 24 * 60))


def _parse_invalid_before() -> datetime | None:
    raw = os.getenv("ADMIN_TOKENS_INVALID_BEFORE", "").strip()
    if not raw:
        return None

    # Supports unix timestamp or ISO-8601 datetime.
    try:
        return datetime.fromtimestamp(int(raw), tz=UTC)
    except ValueError:
        pass

    try:
        iso = raw.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(iso)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tz=UTC)
        return parsed.astimezone(UTC)
    except ValueError:
        return None


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
        "iat": int(datetime.now(UTC).timestamp()),
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
    try:
        expected_signature = _sign(signing_input)
    except RuntimeError:
        return None
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
        issued_at = datetime.fromtimestamp(int(payload.get("iat", 0)), tz=UTC)
        expires_at = datetime.fromtimestamp(int(payload["exp"]), tz=UTC)
        if expires_at < datetime.now(UTC):
            return None

        invalid_before = _parse_invalid_before()
        if invalid_before and issued_at < invalid_before:
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
    configured_ttl = _get_ttl_minutes(ttl_minutes)
    expires_at = datetime.now(UTC) + timedelta(minutes=configured_ttl)
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
