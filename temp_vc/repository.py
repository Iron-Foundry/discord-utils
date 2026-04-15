from __future__ import annotations

import json

import asyncpg
from loguru import logger

from temp_vc.models import TempVCConfig, TempVCUserSettings

_DDL = """
CREATE TABLE IF NOT EXISTS temp_vc_config (
    guild_id                    BIGINT PRIMARY KEY,
    trigger_channel_id          BIGINT,
    trigger_channel_category_id BIGINT,
    active_channels             JSONB  NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS temp_vc_user_settings (
    user_id  BIGINT  NOT NULL,
    guild_id BIGINT  NOT NULL,
    private  BOOLEAN NOT NULL DEFAULT FALSE,
    whitelist JSONB  NOT NULL DEFAULT '[]',
    PRIMARY KEY (user_id, guild_id)
);
"""


class PgTempVCRepository:
    """PostgreSQL-backed repository for temp VC config and user settings."""

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
        logger.debug("PgTempVCRepository: tables ensured")

    async def get_config(self, guild_id: int) -> TempVCConfig | None:
        pool = await self._pool_()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM temp_vc_config WHERE guild_id = $1", guild_id
            )
        if not row:
            return None
        raw: dict = json.loads(row["active_channels"]) if row["active_channels"] else {}
        return TempVCConfig(
            guild_id=row["guild_id"],
            trigger_channel_id=row["trigger_channel_id"],
            trigger_channel_category_id=row["trigger_channel_category_id"],
            active_channels={int(k): int(v) for k, v in raw.items()},
        )

    async def save_config(self, config: TempVCConfig) -> None:
        active_json = json.dumps(
            {str(k): v for k, v in config.active_channels.items()}
        )
        pool = await self._pool_()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO temp_vc_config
                    (guild_id, trigger_channel_id, trigger_channel_category_id,
                     active_channels)
                VALUES ($1, $2, $3, $4::jsonb)
                ON CONFLICT (guild_id) DO UPDATE SET
                    trigger_channel_id          = EXCLUDED.trigger_channel_id,
                    trigger_channel_category_id = EXCLUDED.trigger_channel_category_id,
                    active_channels             = EXCLUDED.active_channels
                """,
                config.guild_id,
                config.trigger_channel_id,
                config.trigger_channel_category_id,
                active_json,
            )

    async def get_user_settings(
        self, user_id: int, guild_id: int
    ) -> TempVCUserSettings | None:
        pool = await self._pool_()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM temp_vc_user_settings"
                " WHERE user_id = $1 AND guild_id = $2",
                user_id,
                guild_id,
            )
        if not row:
            return None
        whitelist: list = json.loads(row["whitelist"]) if row["whitelist"] else []
        return TempVCUserSettings(
            user_id=row["user_id"],
            guild_id=row["guild_id"],
            private=row["private"],
            whitelist=[int(x) for x in whitelist],
        )

    async def save_user_settings(self, settings: TempVCUserSettings) -> None:
        whitelist_json = json.dumps(settings.whitelist)
        pool = await self._pool_()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO temp_vc_user_settings (user_id, guild_id, private, whitelist)
                VALUES ($1, $2, $3, $4::jsonb)
                ON CONFLICT (user_id, guild_id) DO UPDATE SET
                    private   = EXCLUDED.private,
                    whitelist = EXCLUDED.whitelist
                """,
                settings.user_id,
                settings.guild_id,
                settings.private,
                whitelist_json,
            )
