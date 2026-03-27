from datetime import UTC, datetime

import bcrypt

from app.services.admin_auth import (
    AdminSession,
    create_access_token,
    get_session,
    hash_password,
    parse_bearer_token,
    revoke_token,
    verify_password,
)


def _session() -> AdminSession:
    return AdminSession(
        user_id="u1",
        email="admin@example.com",
        display_name="Admin",
        is_admin=True,
        expires_at=datetime.now(UTC),
    )


def test_create_access_token_sets_expiration_in_future():
    token, expires_at = create_access_token(_session(), ttl_minutes=1)

    assert token
    assert expires_at > datetime.now(UTC)


def test_get_session_roundtrip_for_valid_token():
    token, _ = create_access_token(_session(), ttl_minutes=5)

    session = get_session(token)
    assert session is not None
    assert session.user_id == "u1"
    assert session.email == "admin@example.com"
    assert session.is_admin is True


def test_get_session_returns_none_for_expired_token():
    token, _ = create_access_token(_session(), ttl_minutes=-1)

    assert get_session(token) is None


def test_get_session_returns_none_for_tampered_token():
    token, _ = create_access_token(_session(), ttl_minutes=5)
    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")

    assert get_session(tampered) is None


def test_parse_bearer_token():
    assert parse_bearer_token(None) is None
    assert parse_bearer_token("Token abc") is None
    assert parse_bearer_token("Bearer   ") is None
    assert parse_bearer_token("Bearer abc") == "abc"


def test_verify_password_bcrypt():
    plain = "password123"
    hashed = bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

    # Valid bcrypt
    is_valid, needs_rehash = verify_password(plain, hashed)
    assert is_valid is True
    assert needs_rehash is False

    # Invalid bcrypt
    is_valid, needs_rehash = verify_password("wrong", hashed)
    assert is_valid is False
    assert needs_rehash is False


def test_verify_password_legacy_plaintext():
    plain = "legacy_pass"

    # Valid plaintext
    is_valid, needs_rehash = verify_password(plain, plain)
    assert is_valid is True
    assert needs_rehash is True

    # Invalid plaintext
    is_valid, needs_rehash = verify_password("wrong", plain)
    assert is_valid is False
    assert needs_rehash is False


def test_hash_password():
    plain = "new_pass"
    hashed = hash_password(plain)
    assert hashed.startswith("$2b$")
    assert bcrypt.checkpw(plain.encode(), hashed.encode())


def test_revoke_token_is_noop_for_stateless_tokens():
    token, _ = create_access_token(_session(), ttl_minutes=5)

    revoke_token(token)
    assert get_session(token) is not None
