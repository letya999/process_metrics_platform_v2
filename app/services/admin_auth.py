"""Simple in-memory token auth for admin endpoints."""

import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import bcrypt

MAX_TOKEN_STORE_SIZE = 1000


@dataclass
class AdminSession:
    user_id: str
    email: str
    display_name: str
    is_admin: bool
    expires_at: datetime


_TOKEN_STORE: dict[str, AdminSession] = {}


def create_token(ttl_minutes: int = 480) -> tuple[str, datetime]:
    token = secrets.token_urlsafe(48)
    expires_at = datetime.now(UTC) + timedelta(minutes=ttl_minutes)
    return token, expires_at


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
    # Legacy plaintext path — constant-time compare to avoid timing attacks
    valid = hmac.compare_digest(plain, stored)
    return (
        valid,
        valid,
    )  # needs_rehash only when valid (no point rehashing wrong password)


def _purge_expired() -> None:
    now = datetime.now(UTC)
    expired_keys = [k for k, s in _TOKEN_STORE.items() if s.expires_at < now]
    for k in expired_keys:
        _TOKEN_STORE.pop(k, None)


def save_session(token: str, session: AdminSession) -> None:
    if len(_TOKEN_STORE) >= MAX_TOKEN_STORE_SIZE:
        _purge_expired()
        if len(_TOKEN_STORE) >= MAX_TOKEN_STORE_SIZE:
            # Evict oldest half by expiry
            sorted_keys = sorted(_TOKEN_STORE, key=lambda k: _TOKEN_STORE[k].expires_at)
            for k in sorted_keys[: MAX_TOKEN_STORE_SIZE // 2]:
                _TOKEN_STORE.pop(k, None)
    _TOKEN_STORE[token] = session


def get_session(token: str) -> AdminSession | None:
    session = _TOKEN_STORE.get(token)
    if not session:
        return None
    if session.expires_at < datetime.now(UTC):
        _TOKEN_STORE.pop(token, None)
        return None
    return session


def revoke_token(token: str) -> None:
    _TOKEN_STORE.pop(token, None)


def parse_bearer_token(auth_header: str | None) -> str | None:
    if not auth_header:
        return None
    prefix = "Bearer "
    if not auth_header.startswith(prefix):
        return None
    token = auth_header[len(prefix) :].strip()
    return token or None
