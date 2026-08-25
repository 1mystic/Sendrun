"""Async SQLAlchemy engine/session setup, shared by the API and the worker.

One engine, one sessionmaker, imported everywhere else. Never construct a second
engine in a router or task module — connection pools are expensive and pool
exhaustion under load is a real failure mode, not a theoretical one.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    # SQLite has no real connection pool; NullPool avoids "database is locked"
    # errors under pytest-asyncio's per-test event loops.
    kwargs = {"echo": settings.sql_echo}
    if settings.database_url.startswith("sqlite"):
        from sqlalchemy.pool import NullPool

        kwargs["poolclass"] = NullPool
    return create_async_engine(settings.database_url, **kwargs)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency. Yields one session per request, always closed."""
    async with get_sessionmaker()() as session:
        yield session
