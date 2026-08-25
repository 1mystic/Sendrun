"""Shared fixtures: an in-memory SQLite DB per test, and an ASGI HTTP client
wired to it via FastAPI's dependency override — never a real Postgres connection
in the unit/integration suite."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from packages.shared.db import get_db
from packages.shared.models import Base
from services.api.main import app


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    # StaticPool: one shared in-memory connection for the whole test, so tables
    # created in setup are visible to the app's own session.
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    async def _get_db_override():
        yield db_session

    app.dependency_overrides[get_db] = _get_db_override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
