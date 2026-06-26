"""
Asaas (اثاثہ) — Test Configuration

Set TEST_DATABASE_URL in .env or environment to run DB-dependent tests.
Pure unit tests (no db_session fixture) always run regardless.
All calculations handled as Decimal (RULES.md A2.6).
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import AsyncGenerator

# On Windows, asyncpg's SSL connections (Supabase requires SSL) cannot be torn
# down cleanly on the default ProactorEventLoop — each per-test loop close leaks
# "Connection._cancel was never awaited" / "Event loop is closed" errors and
# orphans server-side connections (tripping the pooler's client cap). The
# Selector loop tears them down cleanly. Must be set before any loop is created.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import pytest
import pytest_asyncio
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

# Load backend/.env so TEST_DATABASE_URL / TEST_DB_SCHEMA defined there are
# visible (os.getenv does not read .env on its own).
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.core.config import get_settings
from app.core.db import Base, get_db
from app.main import app

settings = get_settings()

# TEST_DATABASE_URL must be set explicitly — no fragile URL mangling.
# Example: postgresql+asyncpg://postgres:password@localhost:5432/asaas_test
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "")

# Optional: isolate tests inside a dedicated schema of the SAME database
# (e.g. test_schema on Supabase). When set, every test connection pins
# search_path to this schema so DDL/queries never touch production (public).
# NOTE: this must be applied via asyncpg server_settings — the libpq-style
# `?options=-csearch_path%3D...` URL param is NOT honoured by SQLAlchemy+asyncpg.
TEST_DB_SCHEMA = os.getenv("TEST_DB_SCHEMA", "").strip()

_db_available = bool(TEST_DATABASE_URL)

# Always defined (used by the per-test engine in db_session too).
_connect_args: dict = {}
if TEST_DB_SCHEMA:
    _connect_args["server_settings"] = {"search_path": TEST_DB_SCHEMA}

if _db_available:
    test_engine = create_async_engine(
        TEST_DATABASE_URL,
        pool_pre_ping=True,
        poolclass=NullPool,
        connect_args=_connect_args,
    )
    test_async_session_factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
else:
    test_engine = None  # type: ignore[assignment]
    test_async_session_factory = None  # type: ignore[assignment]


async def _create_schema() -> None:
    """Create (and verify isolation of) the test schema, then build all tables."""
    async with test_engine.begin() as conn:
        if TEST_DB_SCHEMA:
            await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{TEST_DB_SCHEMA}"'))
            search_path = (await conn.execute(text("show search_path"))).scalar()
            # Resolve the *schema* an unqualified 'users' points at. None = no such
            # table yet (safe); our test schema = our own table (safe); anything
            # else (e.g. 'public') = production leak → abort before any drop_all.
            ns = (await conn.execute(text(
                "select n.nspname from pg_class c "
                "join pg_namespace n on n.oid = c.relnamespace "
                "where c.oid = to_regclass('users')"
            ))).scalar()
            if ns is not None and ns != TEST_DB_SCHEMA:
                raise RuntimeError(
                    f"ABORTING tests: schema isolation failed — unqualified 'users' "
                    f"resolves to schema '{ns}', not '{TEST_DB_SCHEMA}' "
                    f"(search_path={search_path!r}). Refusing to drop_all against "
                    f"what may be production data."
                )
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


async def _drop_schema() -> None:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest.fixture(scope="session")
def setup_test_db():
    """Create all tables before testing, drop them after the session ends.

    Synchronous on purpose: a session-scoped *async* fixture cannot be pulled in
    by the function-scoped async ``db_session`` fixture (pytest-asyncio drives
    them on different event-loop runners). Running the async setup via
    ``asyncio.run`` here sidesteps that loop-scope conflict. NullPool means each
    call gets a fresh connection, so reusing the engine across loops is safe.

    Safety: when TEST_DB_SCHEMA isolates tests inside a shared database, abort if
    an unqualified table name resolves to a production table — never drop_all
    against production.
    """
    if not _db_available:
        pytest.skip("TEST_DATABASE_URL not set — skipping DB test")
    asyncio.run(_create_schema())
    yield
    asyncio.run(_drop_schema())


@pytest_asyncio.fixture
async def db_session(setup_test_db) -> AsyncGenerator[AsyncSession, None]:
    """Transactional DB session; also wires FastAPI get_db override for the test.

    Depends on ``setup_test_db`` as a parameter (not getfixturevalue) so the
    sync session-scoped schema setup runs during fixture resolution — before this
    coroutine's event loop starts — avoiding "asyncio.run() from a running loop".

    Builds a fresh engine *inside this test's event loop* and disposes it before
    the loop closes. pytest-asyncio gives each test its own loop, and asyncpg
    connections are loop-bound — a shared module engine leaks connections that
    cannot be closed across loops, which on Supabase's session-mode pooler
    quickly trips the 15-client cap (EMAXCONNSESSION). Per-test create+dispose
    keeps every connection's lifecycle within one loop.
    """
    engine = create_async_engine(
        TEST_DATABASE_URL,
        poolclass=NullPool,
        connect_args=_connect_args,
    )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:

            async def _get_db():
                yield session

            app.dependency_overrides[get_db] = _get_db
            try:
                yield session
            finally:
                app.dependency_overrides.pop(get_db, None)
                await session.rollback()
    finally:
        await engine.dispose()
