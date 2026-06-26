"""
Asaas (اثاثہ) — Database Setup

Async SQLAlchemy engine + session factory.
Uses NullPool so PgBouncer (Supabase pooler) manages connections (RULES.md A3.1).
"""

from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

# Persistent client-side pool over the Supabase transaction pooler (PgBouncer,
# :6543). NullPool was opening a fresh DNS+TCP+TLS connection on EVERY request —
# slow (hundreds of ms of round-trips before each query) and fragile (any
# transient DNS/network blip failed the whole request → 500 "Couldn't load").
# A warm pool reuses live connections, and:
#   * pool_pre_ping  — checks a connection is alive before use and transparently
#                      reconnects a dead/dropped one instead of erroring.
#   * pool_recycle   — drops connections older than 5 min (the pooler silently
#                      closes idle ones) so we never hand out a stale socket.
#   * statement_cache_size=0 — required for PgBouncer transaction mode (no
#                      server-side prepared statements).
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_timeout=10,
    connect_args={
        "statement_cache_size": 0,
        "timeout": 10,          # connection-establishment timeout (s)
        "command_timeout": 30,  # per-query timeout (s) — fail fast, never hang
    },
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields an async DB session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
