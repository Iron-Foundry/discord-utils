from __future__ import annotations

from loguru import logger
from pymongo import ASCENDING, AsyncMongoClient
from pymongo.errors import PyMongoError

from temp_vc.models import TempVCConfig


class MongoTempVCRepository:
    """MongoDB persistence for the temp VC service."""

    def __init__(self, mongo_uri: str, db_name: str) -> None:
        self._client = AsyncMongoClient(mongo_uri)
        self._db = self._client[db_name]
        self._configs = self._db["temp_vc"]

    async def ensure_indexes(self) -> None:
        """Create indexes on startup. Safe to call multiple times."""
        await self._configs.create_index([("guild_id", ASCENDING)], unique=True)
        logger.info("MongoTempVCRepository: indexes ensured")

    async def get_config(self, guild_id: int) -> TempVCConfig | None:
        """Return the temp VC config for the guild, or None if not configured."""
        try:
            doc = await self._configs.find_one({"guild_id": guild_id}, {"_id": 0})
            if doc:
                logger.debug(
                    f"MongoTempVCRepository: loaded config for guild {guild_id}"
                )
            else:
                logger.debug(f"MongoTempVCRepository: no config for guild {guild_id}")
            return TempVCConfig.model_validate(doc) if doc else None
        except PyMongoError as e:
            logger.error(f"Failed to fetch temp VC config for guild {guild_id}: {e}")
            return None

    async def save_config(self, config: TempVCConfig) -> None:
        """Upsert the temp VC config for the guild."""
        try:
            doc = config.model_dump(mode="json")
            await self._configs.replace_one(
                {"guild_id": config.guild_id}, doc, upsert=True
            )
            logger.debug(
                f"MongoTempVCRepository: saved config for guild {config.guild_id}"
            )
        except PyMongoError as e:
            logger.error(
                f"Failed to save temp VC config for guild {config.guild_id}: {e}"
            )
