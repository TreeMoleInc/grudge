"""Integration-tier fixtures: real Postgres, real migrated schema, real FastAPI
app over httpx. Gated on GRUDGE_TEST_DATABASE_URL (deliberately separate from the
app's own runtime DATABASE_URL) being set - mirrors engine/'s GRUDGE_TEST_NSJAIL=1
gating pattern for its WSL2-only tier. Unit tests (tests/unit/) don't use any of
this and run anywhere.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from grudge_backend.auth.session import create_session
from grudge_backend.config import settings
from grudge_backend.models.user import User

TEST_DATABASE_URL = os.environ.get("GRUDGE_TEST_DATABASE_URL")

requires_db = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="set GRUDGE_TEST_DATABASE_URL to run integration tests"
)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if "integration" in str(item.fspath):
            item.add_marker(requires_db)
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session", autouse=True)
def _migrated_schema() -> None:
    """Applies migrations to GRUDGE_TEST_DATABASE_URL once per test session
    (idempotent - alembic no-ops if already at head) so every integration test
    can assume the schema already exists.
    """
    if not TEST_DATABASE_URL:
        return
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(Path(__file__).parent.parent / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(cfg, "head")


@pytest_asyncio.fixture(scope="session")
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    if not TEST_DATABASE_URL:
        pytest.skip("GRUDGE_TEST_DATABASE_URL not set")
    eng = create_async_engine(TEST_DATABASE_URL)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Savepoint-per-test: the whole test runs inside one outer transaction that
    is always rolled back at the end, with the AsyncSession joined to it via a
    nested savepoint - so endpoint code calling commit() doesn't actually
    persist anything across tests, and there's never any truncation needed.
    """
    async with engine.connect() as connection:
        trans = await connection.begin()
        session_factory = async_sessionmaker(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        session = session_factory()
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    from grudge_backend.db import get_db
    from grudge_backend.main import app

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def make_user(db_session: AsyncSession, *, username: str) -> User:
    user = User(username=username)
    db_session.add(user)
    await db_session.flush()
    return user


async def log_in_as(client: AsyncClient, db_session: AsyncSession, user: User) -> None:
    raw_token = await create_session(db_session, user_id=user.id)
    client.cookies.set(settings.session_cookie_name, raw_token)


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    return await make_user(db_session, username="alice")


@pytest_asyncio.fixture
async def other_user(db_session: AsyncSession) -> User:
    return await make_user(db_session, username="bob")


@pytest.fixture
def login():
    """Exposes log_in_as as a fixture so tests needing to log in as a SECOND
    user mid-test (e.g. cross-user ownership checks) don't need to import from
    this file directly - just request `login` like any other fixture.
    """
    return log_in_as


@pytest_asyncio.fixture
async def auth_client(client: AsyncClient, db_session: AsyncSession, user: User) -> AsyncClient:
    """A client logged in as `user` - the common case for endpoint tests."""
    await log_in_as(client, db_session, user)
    return client


@pytest.fixture
def worker_session_maker(db_session: AsyncSession):
    """Matches the `() -> async context manager yielding AsyncSession` shape
    grudge_backend.worker.process_job expects for its `session_maker` param
    (default: the real app-wide async_session_maker, which opens a genuinely
    separate DB connection per call - unusable in tests, since it wouldn't see
    this test's uncommitted savepoint data). This always yields the SAME
    `db_session`, so process_job's several internal `async with session_maker()
    as db:` blocks all see what the test fixture set up - safe because
    AsyncSession is fine to reuse sequentially within one test, and repeated
    `.commit()` calls on a savepoint-joined session just release/reopen the
    nested savepoint (the same property the rest of this test suite already
    relies on for router code that calls commit()).
    """

    class _SessionCM:
        async def __aenter__(self) -> AsyncSession:
            return db_session

        async def __aexit__(self, *exc_info: object) -> bool:
            return False

    return lambda: _SessionCM()


async def make_player(
    db_session: AsyncSession, *, username: str, rating: int = 1000
) -> tuple[AsyncClient, User]:
    """A fresh AsyncClient (its own cookie jar) logged in as a new user -
    for tests needing several *simultaneously* authenticated users against the
    same app/db_session (matchmaking room-fill tests), where the single
    `client`/`auth_client` fixtures (one cookie jar each) aren't enough.
    Requires something to have already requested the `client` fixture once in
    the same test, so `app.dependency_overrides[get_db]` is already pointed at
    this test's db_session before this constructs additional AsyncClients
    against the same app.
    """
    from grudge_backend.main import app

    user = await make_user(db_session, username=username)
    user.rating = rating
    await db_session.flush()
    player_client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    await log_in_as(player_client, db_session, user)
    return player_client, user
