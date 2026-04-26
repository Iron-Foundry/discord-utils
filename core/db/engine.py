"""Async SQLAlchemy engine and session factory for discord-utils."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.db.models import Base

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_engine(pg_uri: str) -> None:
    """Create the shared engine and session factory.

    pg_uri must use the postgresql+asyncpg:// scheme.
    Call once at startup before any repository is used.
    """
    global _engine, _session_factory
    _engine = create_async_engine(pg_uri, pool_pre_ping=True)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("DB engine not initialised - call init_engine() first")
    return _session_factory


async def ensure_tables() -> None:
    """Create all tables that do not already exist.

    Uses SQLAlchemy metadata so schema stays in sync with the ORM models.
    Skips the shared `users` table (owned by api-backend / Alembic).
    """
    if _engine is None:
        raise RuntimeError("DB engine not initialised - call init_engine() first")
    async with _engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[
                Base.metadata.tables["temp_vc_config"],
                Base.metadata.tables["temp_vc_user_settings"],
                Base.metadata.tables["clan_events_config"],
            ],
        )
