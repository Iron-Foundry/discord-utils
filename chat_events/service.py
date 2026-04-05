from __future__ import annotations

import asyncio
import hashlib
import json
from typing import TYPE_CHECKING, Any

import discord
from loguru import logger
from valkey.asyncio import Valkey

from chat_events.models import ClanEventsConfig
from chat_events.repository import MongoChatEventsRepository
from core.service_base import Service

if TYPE_CHECKING:
    pass

STREAM_KEY = "foundry:clan_events"
CONSUMER_GROUP = "discord-utils"
CONSUMER_NAME = "discord-utils-1"
BLOCK_MS = 5000
DEDUP_TTL_SECONDS = 30
DEDUP_KEY_PREFIX = "foundry:dedup:"


class ChatEventsService(Service):
    """Consumes clan events from Valkey and posts Discord embeds."""

    def __init__(
        self,
        guild: discord.Guild,
        repo: MongoChatEventsRepository,
        valkey: Valkey,
        client: discord.Client,
    ) -> None:
        self._guild = guild
        self._repo = repo
        self._valkey = valkey
        self._client = client
        self._config: ClanEventsConfig | None = None
        self._consumer_task: asyncio.Task[None] | None = None

    async def initialize(self) -> None:
        """Load config, ensure indexes, and create the consumer group."""
        await self._repo.ensure_indexes()
        self._config = await self._repo.get_config(self._guild.id)
        if self._config is None:
            self._config = ClanEventsConfig(guild_id=self._guild.id)
        await self._ensure_consumer_group()
        logger.info("ChatEventsService: initialized")

    async def post_ready(self) -> None:
        """Start the background stream consumer after the bot is connected."""
        self._consumer_task = asyncio.create_task(
            self._consume(), name="clan-events-consumer"
        )
        logger.info("ChatEventsService: consumer task started")

    # ------------------------------------------------------------------
    # Config management
    # ------------------------------------------------------------------

    async def set_channel(self, channel_id: int) -> None:
        """Persist the configured Discord channel."""
        assert self._config is not None
        self._config.channel_id = channel_id
        await self._repo.save_config(self._config)

    @property
    def channel_id(self) -> int | None:
        """The configured channel ID, or None if not set."""
        return self._config.channel_id if self._config else None

    # ------------------------------------------------------------------
    # Stream consumer
    # ------------------------------------------------------------------

    async def _ensure_consumer_group(self) -> None:
        """Create the consumer group if it does not already exist."""
        try:
            await self._valkey.xgroup_create(
                STREAM_KEY, CONSUMER_GROUP, id="0", mkstream=True
            )
            logger.info(
                "ChatEventsService: consumer group '{}' created", CONSUMER_GROUP
            )
        except Exception as exc:
            # BUSYGROUP means the group already exists — that's fine
            if "BUSYGROUP" in str(exc):
                logger.debug(
                    "ChatEventsService: consumer group '{}' already exists",
                    CONSUMER_GROUP,
                )
            else:
                logger.error(
                    "ChatEventsService: failed to create consumer group: {}", exc
                )

    async def _consume(self) -> None:
        """Continuously read from the Valkey stream and dispatch events."""
        logger.info("ChatEventsService: consumer loop running")
        while True:
            try:
                results = await self._valkey.xreadgroup(
                    groupname=CONSUMER_GROUP,
                    consumername=CONSUMER_NAME,
                    streams={STREAM_KEY: ">"},
                    count=10,
                    block=BLOCK_MS,
                )
                if not results:
                    continue
                for _stream, messages in results:
                    for msg_id, fields in messages:
                        await self._handle_message(msg_id, fields)
            except asyncio.CancelledError:
                logger.info("ChatEventsService: consumer task cancelled")
                return
            except Exception as exc:
                logger.error("ChatEventsService: consumer error: {}", exc)
                await asyncio.sleep(2)

    async def _is_duplicate(self, event_type: str, data: dict[str, Any]) -> bool:
        """Return True if an identical event was dispatched within the dedup window."""
        dedup_data = {k: v for k, v in data.items() if k != "userkey"}
        raw = f"{event_type}:{json.dumps(dedup_data, sort_keys=True)}"
        fingerprint = hashlib.sha256(raw.encode()).hexdigest()
        key = f"{DEDUP_KEY_PREFIX}{fingerprint}"
        result = await self._valkey.set(key, "1", nx=True, ex=DEDUP_TTL_SECONDS)
        return result is None  # None → key already existed → duplicate

    async def _handle_message(self, msg_id: bytes, fields: dict[bytes, bytes]) -> None:
        """Dispatch a single stream message, then ACK it."""
        try:
            event_type = fields[b"type"].decode()
            data: dict[str, Any] = json.loads(fields[b"data"])
            if await self._is_duplicate(event_type, data):
                logger.debug(
                    "ChatEventsService: duplicate event '{}', skipping", event_type
                )
            else:
                await self._dispatch(event_type, data)
        except Exception as exc:
            logger.error(
                "ChatEventsService: failed to dispatch msg {}: {}", msg_id, exc
            )
        finally:
            await self._valkey.xack(STREAM_KEY, CONSUMER_GROUP, msg_id)

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def _dispatch(self, event_type: str, data: dict[str, Any]) -> None:
        """Route an event to the right embed builder and post to Discord."""
        if not self._config or not self._config.channel_id:
            return

        channel = self._guild.get_channel_or_thread(self._config.channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            logger.warning(
                "ChatEventsService: configured channel {} not found or not a text channel/thread",
                self._config.channel_id,
            )
            return

        if event_type == "chat":
            content = self._chat_message(data)
            await channel.send(content)
        else:
            embed = self._build_embed(event_type, data)
            if embed:
                await channel.send(embed=embed)

    def _build_embed(
        self, event_type: str, data: dict[str, Any]
    ) -> discord.Embed | None:
        """Route to the correct embed builder by event type."""
        builders = {
            "loot": self._loot_embed,
            "levelup": self._levelup_embed,
            "achievement": self._achievement_embed,
            "pet": self._pet_embed,
            "new_member": self._new_member_embed,
        }
        builder = builders.get(event_type)
        if builder is None:
            logger.debug("ChatEventsService: unknown event type '{}'", event_type)
            return None
        return builder(data)

    # ------------------------------------------------------------------
    # Embed builders
    # ------------------------------------------------------------------

    def _loot_embed(self, data: dict[str, Any]) -> discord.Embed:
        player = data.get("player_name", "Unknown")
        item = data.get("item_name", "Unknown item")
        gp = data.get("coin_value", 0)
        source = data.get("source", "Unknown source")
        embed = discord.Embed(
            description=f"**{player}** received **{item}** ({gp:,} gp) from **{source}**",
            color=discord.Color.gold(),
        )
        embed.set_author(name="Loot Drop")
        return embed

    def _levelup_embed(self, data: dict[str, Any]) -> discord.Embed:
        player = data.get("player_name", "Unknown")
        skill = data.get("skill", "Unknown skill")
        level = data.get("new_level", "?")
        embed = discord.Embed(
            description=f"**{player}** reached level **{level} {skill}**",
            color=discord.Color.blue(),
        )
        embed.set_author(name="Level Up!")
        return embed

    def _achievement_embed(self, data: dict[str, Any]) -> discord.Embed:
        player = data.get("player_name", "Unknown")
        name = data.get("name", "Unknown achievement")
        embed = discord.Embed(
            description=f"**{player}** completed **{name}**",
            color=discord.Color.purple(),
        )
        embed.set_author(name="Achievement Unlocked")
        return embed

    def _pet_embed(self, data: dict[str, Any]) -> discord.Embed:
        player = data.get("player_name", "Unknown")
        embed = discord.Embed(
            description=f"**{player}** received a pet!",
            color=discord.Color.green(),
        )
        embed.set_author(name="Pet Drop!")
        return embed

    def _new_member_embed(self, data: dict[str, Any]) -> discord.Embed:
        player = data.get("player_name", "Unknown")
        embed = discord.Embed(
            description=f"**{player}** has joined the clan",
            color=discord.Color.teal(),
        )
        embed.set_author(name="New Member")
        return embed

    # ------------------------------------------------------------------
    # Chat relay
    # ------------------------------------------------------------------

    def _chat_message(self, data: dict[str, Any]) -> str:
        rank = data.get("rank", "")
        player = data.get("player_name", data.get("sender", "Unknown"))
        message = data.get("raw_message", "")
        if rank:
            return f"[{rank}] {player}: {message}"
        return f"{player}: {message}"
