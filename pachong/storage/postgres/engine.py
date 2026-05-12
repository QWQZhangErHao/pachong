"""asyncpg engine factory with connection pooling."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from pachong.core.settings import Settings
from pachong.storage.postgres.models import Base

_engine = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


async def init_postgres(settings: Settings) -> None:
    """Initialize async engine and session factory. Call once at startup."""
    global _engine, _sessionmaker

    _engine = create_async_engine(
        settings.database.postgres_dsn,
        pool_size=settings.database.postgres_pool_min,
        max_overflow=settings.database.postgres_pool_max - settings.database.postgres_pool_min,
        pool_pre_ping=True,
        echo=False,
    )
    _sessionmaker = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def create_tables() -> None:
    """Create all tables if they don't exist. For dev use only — prefer Alembic in prod."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """Get an async session from the pool."""
    if _sessionmaker is None:
        raise RuntimeError("Postgres not initialized. Call init_postgres() first.")
    return _sessionmaker()


async def close_postgres() -> None:
    """Close the engine and all connections."""
    if _engine:
        await _engine.dispose()
