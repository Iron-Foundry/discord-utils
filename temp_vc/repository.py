from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from core.db import engine as db_engine
from core.db.models import TempVCConfig as TempVCConfigORM
from core.db.models import TempVCUserSettings as TempVCUserSettingsORM
from temp_vc.models import TempVCConfig, TempVCUserSettings


class PgTempVCRepository:
    """SQLAlchemy-backed repository for temp VC config and user settings."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def ensure_tables(self) -> None:
        """Delegate table creation to the shared engine helper."""
        await db_engine.ensure_tables()

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    async def get_config(self, guild_id: int) -> TempVCConfig | None:
        async with self._sf() as session:
            row = await session.get(TempVCConfigORM, guild_id)
        if row is None:
            return None
        return TempVCConfig(
            guild_id=row.guild_id,
            trigger_channel_id=row.trigger_channel_id,
            trigger_channel_category_id=row.trigger_channel_category_id,
            active_channels={int(k): int(v) for k, v in (row.active_channels or {}).items()},
        )

    async def save_config(self, config: TempVCConfig) -> None:
        stmt = (
            insert(TempVCConfigORM)
            .values(
                guild_id=config.guild_id,
                trigger_channel_id=config.trigger_channel_id,
                trigger_channel_category_id=config.trigger_channel_category_id,
                active_channels={str(k): v for k, v in config.active_channels.items()},
            )
            .on_conflict_do_update(
                index_elements=["guild_id"],
                set_={
                    "trigger_channel_id": config.trigger_channel_id,
                    "trigger_channel_category_id": config.trigger_channel_category_id,
                    "active_channels": {str(k): v for k, v in config.active_channels.items()},
                },
            )
        )
        async with self._sf() as session:
            await session.execute(stmt)
            await session.commit()

    # ------------------------------------------------------------------
    # User settings
    # ------------------------------------------------------------------

    async def get_user_settings(
        self, user_id: int, guild_id: int
    ) -> TempVCUserSettings | None:
        async with self._sf() as session:
            row = await session.get(TempVCUserSettingsORM, (user_id, guild_id))
        if row is None:
            return None
        return TempVCUserSettings(
            user_id=row.user_id,
            guild_id=row.guild_id,
            private=row.private,
            whitelist=[int(x) for x in (row.whitelist or [])],
        )

    async def save_user_settings(self, settings: TempVCUserSettings) -> None:
        stmt = (
            insert(TempVCUserSettingsORM)
            .values(
                user_id=settings.user_id,
                guild_id=settings.guild_id,
                private=settings.private,
                whitelist=settings.whitelist,
            )
            .on_conflict_do_update(
                index_elements=["user_id", "guild_id"],
                set_={
                    "private": settings.private,
                    "whitelist": settings.whitelist,
                },
            )
        )
        async with self._sf() as session:
            await session.execute(stmt)
            await session.commit()
