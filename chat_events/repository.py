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

    async def get_sender_info(
        self, discord_user_id: int
    ) -> tuple[str, str | None] | None:
        """Return (rsn, clan_rank) for a Discord user, or None if no profile / RSN."""
        try:
            doc = await self._db["users"].find_one(
                {"discord_user_id": discord_user_id, "rsn": {"$ne": None}},
                {"rsn": 1, "clan_rank": 1, "_id": 0},
            )
            if not doc:
                return None
            return doc["rsn"], doc.get("clan_rank")
        except PyMongoError as e:
            logger.error(f"Failed to fetch sender info for user {discord_user_id}: {e}")
            return None

    async def get_discord_user_id_by_rsn(self, rsn: str) -> int | None:
        """Return the discord_user_id for the given RSN, or None if not found."""
        try:
            doc = await self._db["users"].find_one(
                {"rsn": {"$regex": f"^{rsn}$", "$options": "i"}},
                {"discord_user_id": 1, "_id": 0},
            )
            return doc["discord_user_id"] if doc else None
        except PyMongoError as e:
            logger.error(f"Failed to fetch discord_user_id for rsn {rsn!r}: {e}")
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
