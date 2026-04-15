from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from core.db import engine as db_engine
from core.db.models import ClanEventsConfig as ClanEventsConfigORM
from core.db.models import User
from chat_events.models import ClanEventsConfig


class PgChatEventsRepository:
    """SQLAlchemy-backed repository for clan events config."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def ensure_tables(self) -> None:
        """Delegate table creation to the shared engine helper."""
        await db_engine.ensure_tables()

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    async def get_config(self, guild_id: int) -> ClanEventsConfig | None:
        async with self._sf() as session:
            row = await session.get(ClanEventsConfigORM, guild_id)
        if row is None:
            return None
        return ClanEventsConfig(guild_id=row.guild_id, channel_id=row.channel_id)

    async def save_config(self, config: ClanEventsConfig) -> None:
        stmt = (
            insert(ClanEventsConfigORM)
            .values(guild_id=config.guild_id, channel_id=config.channel_id)
            .on_conflict_do_update(
                index_elements=["guild_id"],
                set_={"channel_id": config.channel_id},
            )
        )
        async with self._sf() as session:
            await session.execute(stmt)
            await session.commit()

    # ------------------------------------------------------------------
    # User lookup (shared users table)
    # ------------------------------------------------------------------

    async def get_sender_info(
        self, discord_user_id: int
    ) -> tuple[str, str | None] | None:
        """Return (rsn, clan_rank) for a Discord user, or None if not found."""
        async with self._sf() as session:
            row = await session.get(User, discord_user_id)
        if row is None or not row.rsn:
            return None
        return row.rsn, row.clan_rank
