from __future__ import annotations

import json
from typing import TYPE_CHECKING

import discord
from loguru import logger

if TYPE_CHECKING:
    from chat_events.service import ChatEventsService
    from core.discord_client import DiscordClient

DISCORD_CHAT_CHANNEL = "foundry:discord_chat"


def register(service: ChatEventsService, client: DiscordClient) -> None:
    """Register an on_message listener that forwards Discord clan chat to RuneLite."""

    async def on_message(message: discord.Message) -> None:
        if message.author.bot:
            return
        logger.debug(
            "ChatEvents: on_message channel={} configured={}",
            message.channel.id,
            service.channel_id,
        )
        if not service.channel_id or message.channel.id != service.channel_id:
            return
        payload = json.dumps({
            "sender": message.author.display_name,
            "message": message.content,
            "guild_name": message.guild.name if message.guild else "",
        })
        logger.info(
            "ChatEvents: publishing to Valkey sender={} guild={}",
            message.author.display_name,
            message.guild.name if message.guild else "?",
        )
        try:
            receivers = await service._valkey.publish(DISCORD_CHAT_CHANNEL, payload)
            logger.info("ChatEvents: publish OK, {} subscriber(s) received", receivers)
        except Exception as exc:
            logger.warning("ChatEvents: failed to publish discord message: {}", exc)

    client.add_listener(on_message, "on_message")
