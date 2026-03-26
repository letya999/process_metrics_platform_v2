from datetime import UTC, datetime, timedelta

import bcrypt

from app.services.admin_auth import (
    _TOKEN_STORE,
    MAX_TOKEN_STORE_SIZE,
    AdminSession,
    create_token,
    get_session,
    hash_password,
    parse_bearer_token,
    revoke_token,
    save_session,
    verify_password,
)


def test_create_token_sets_expiration_in_future():
    token, expires_at = create_token(ttl_minutes=1)

    assert token
    assert expires_at > datetime.now(UTC)


def test_save_get_and_revoke_session():
    token = "t1"
    session = AdminSession(
        user_id="u1",
        email="admin@example.com",
        display_name="Admin",
        is_admin=True,
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )

    save_session(token, session)
    assert get_session(token) == session

    revoke_token(token)
    assert get_session(token) is None


def test_get_session_removes_expired_session():
    token = "expired"
    _TOKEN_STORE[token] = AdminSession(
        user_id="u1",
        email="admin@example.com",
        display_name="Admin",
        is_admin=True,
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )

    assert get_session(token) is None
    assert token not in _TOKEN_STORE


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


def test_token_store_eviction():
    _TOKEN_STORE.clear()
    now = datetime.now(UTC)

    # Fill store to max
    for i in range(MAX_TOKEN_STORE_SIZE):
        save_session(
            f"token_{i}",
            AdminSession(
                user_id=f"u{i}",
                email=f"u{i}@test.com",
                display_name=f"U{i}",
                is_admin=True,
                expires_at=now + timedelta(minutes=i + 1),
            ),
        )

    assert len(_TOKEN_STORE) == MAX_TOKEN_STORE_SIZE

    # Add one more - should trigger eviction
    # Half of the oldest should be evicted
    save_session(
        "new_token",
        AdminSession(
            user_id="new",
            email="new@test.com",
            display_name="New",
            is_admin=True,
            expires_at=now + timedelta(hours=1),
        ),
    )

    # MAX_TOKEN_STORE_SIZE=1000.
    # save_session(1001) calls _purge_expired (0 purged).
    # Then evicts oldest half (500 evicted).
    # Store size = 1000 - 500 + 1 = 501.
    assert len(_TOKEN_STORE) == (MAX_TOKEN_STORE_SIZE // 2) + 1
    assert "new_token" in _TOKEN_STORE
    assert "token_0" not in _TOKEN_STORE
    assert f"token_{MAX_TOKEN_STORE_SIZE - 1}" in _TOKEN_STORE
