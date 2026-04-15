"""SQLAlchemy ORM models for discord-utils.

Mirrors the tables created by the ensure_tables() DDL helper.
Must stay in sync with the schema defined in core/db/engine.py.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TempVCConfig(Base):
    __tablename__ = "temp_vc_config"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    trigger_channel_id: Mapped[int | None] = mapped_column(BigInteger)
    trigger_channel_category_id: Mapped[int | None] = mapped_column(BigInteger)
    active_channels: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )


class TempVCUserSettings(Base):
    __tablename__ = "temp_vc_user_settings"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    private: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    whitelist: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )


class ClanEventsConfig(Base):
    __tablename__ = "clan_events_config"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    channel_id: Mapped[int | None] = mapped_column(BigInteger)


class User(Base):
    """Read-only view of the shared users table (owned by api-backend)."""

    __tablename__ = "users"

    discord_user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    rsn: Mapped[str | None] = mapped_column(Text)
    clan_rank: Mapped[str | None] = mapped_column(Text)
