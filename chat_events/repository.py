from __future__ import annotations

import asyncpg
from loguru import logger

from chat_events.models import ClanEventsConfig

_DDL = """
CREATE TABLE IF NOT EXISTS clan_events_config (
    guild_id   BIGINT PRIMARY KEY,
    channel_id BIGINT
);
"""


class PgChatEventsRepository:
    """PostgreSQL-backed repository for clan events config."""

    def __init__(self, pg_uri: str) -> None:
        self._pg_uri = pg_uri
        self._pool: asyncpg.Pool | None = None  # type: ignore[type-arg]

    async def _pool_(self) -> asyncpg.Pool:  # type: ignore[type-arg]
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._pg_uri)
        return self._pool

    async def ensure_indexes(self) -> None:
        """Create tables if they do not already exist."""
        pool = await self._pool_()
        async with pool.acquire() as conn:
            await conn.execute(_DDL)
        logger.debug("PgChatEventsRepository: tables ensured")

    async def get_config(self, guild_id: int) -> ClanEventsConfig | None:
        pool = await self._pool_()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM clan_events_config WHERE guild_id = $1", guild_id
            )
        if not row:
            return None
        return ClanEventsConfig(
            guild_id=row["guild_id"],
            channel_id=row["channel_id"],
        )

    async def save_config(self, config: ClanEventsConfig) -> None:
        pool = await self._pool_()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO clan_events_config (guild_id, channel_id)
                VALUES ($1, $2)
                ON CONFLICT (guild_id) DO UPDATE SET
                    channel_id = EXCLUDED.channel_id
                """,
                config.guild_id,
                config.channel_id,
            )

    async def get_sender_info(
        self, discord_user_id: int
    ) -> tuple[str, str | None] | None:
        """Return (rsn, clan_rank) for a Discord user, or None if not found."""
        pool = await self._pool_()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT rsn, clan_rank FROM users WHERE discord_user_id = $1",
                discord_user_id,
            )
        if not row or not row["rsn"]:
            return None
        return row["rsn"], row["clan_rank"]
