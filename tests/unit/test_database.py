"""Unit tests for app.database lifecycle and session handling."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import database


def test_to_async_database_url_variants():
    assert (
        database._to_async_database_url("postgresql://user:pass@host/db")
        == "postgresql+asyncpg://user:pass@host/db"
    )
    assert (
        database._to_async_database_url("postgres://user:pass@host/db")
        == "postgresql+asyncpg://user:pass@host/db"
    )
    assert (
        database._to_async_database_url("sqlite+aiosqlite:///tmp.db")
        == "sqlite+aiosqlite:///tmp.db"
    )


def test_get_async_database_url_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://a:b@localhost:5432/metrics")
    database.reset_db_state_for_tests()
    assert database.get_async_database_url().startswith("postgresql+asyncpg://")


@pytest.mark.asyncio
async def test_get_db_commits_on_success(monkeypatch):
    session = SimpleNamespace(
        commit=AsyncMock(),
        rollback=AsyncMock(),
        close=AsyncMock(),
    )

    class _SessionScope:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(
        database, "get_session_maker", lambda: (lambda: _SessionScope())
    )

    gen = database.get_db()
    yielded = await anext(gen)
    assert yielded is session
    with pytest.raises(StopAsyncIteration):
        await anext(gen)

    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()
    session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_db_rolls_back_on_error(monkeypatch):
    session = SimpleNamespace(
        commit=AsyncMock(),
        rollback=AsyncMock(),
        close=AsyncMock(),
    )

    class _SessionScope:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(
        database, "get_session_maker", lambda: (lambda: _SessionScope())
    )

    gen = database.get_db()
    await anext(gen)
    with pytest.raises(RuntimeError):
        await gen.athrow(RuntimeError("boom"))

    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once()
    session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_init_and_close_db_use_engine(monkeypatch):
    conn = SimpleNamespace(execute=AsyncMock())

    class _ConnScope:
        async def __aenter__(self):
            return conn

        async def __aexit__(self, *_args):
            return False

    engine = SimpleNamespace(begin=lambda: _ConnScope(), dispose=AsyncMock())
    monkeypatch.setattr(database, "get_engine", lambda: engine)

    await database.init_db()
    await database.close_db()

    conn.execute.assert_awaited_once()
    assert "SELECT 1" in str(conn.execute.call_args.args[0])
    engine.dispose.assert_awaited_once()
