from __future__ import annotations

from loguru import logger
from pymongo import ASCENDING, AsyncMongoClient
from pymongo.errors import PyMongoError

from chat_events.models import ClanEventsConfig


class MongoChatEventsRepository:
    """MongoDB persistence for the chat events service."""

    def __init__(self, mongo_uri: str, db_name: str) -> None:
        self._client = AsyncMongoClient(mongo_uri)
        self._db = self._client[db_name]
        self._configs = self._db["chat_events_config"]

    async def ensure_indexes(self) -> None:
        """Create indexes on startup. Safe to call multiple times."""
        await self._configs.create_index([("guild_id", ASCENDING)], unique=True)
        logger.info("MongoChatEventsRepository: indexes ensured")

    async def get_config(self, guild_id: int) -> ClanEventsConfig | None:
        """Return the chat events config for the guild, or None if not configured."""
        try:
            doc = await self._configs.find_one({"guild_id": guild_id}, {"_id": 0})
            return ClanEventsConfig.model_validate(doc) if doc else None
        except PyMongoError as e:
            logger.error(
                f"Failed to fetch chat events config for guild {guild_id}: {e}"
            )
            return None

    async def save_config(self, config: ClanEventsConfig) -> None:
        """Upsert the chat events config for the guild."""
        try:
            doc = config.model_dump(mode="json")
            await self._configs.replace_one(
                {"guild_id": config.guild_id}, doc, upsert=True
            )
            logger.debug(
                f"MongoChatEventsRepository: saved config for guild {config.guild_id}"
            )
        except PyMongoError as e:
            logger.error(
                f"Failed to save chat events config for guild {config.guild_id}: {e}"
            )
