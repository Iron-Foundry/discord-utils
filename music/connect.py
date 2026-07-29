"""Getting a leased bot into the voice channel it was leased for.

Split out of the session manager because both steps are about the player bot's
own view of Discord rather than about sessions: the channel object has to come
from the bot that will connect, and the nickname is set on that bot's member.
"""

from __future__ import annotations

import discord
from loguru import logger


def own_channel(
    client: discord.Client, channel_id: int, bot_index: int
) -> discord.VoiceChannel:
    """Re-resolve a channel through the bot that will actually connect.

    The orchestrator's copy of the channel belongs to the orchestrator's client,
    so connecting with it would put the orchestrator in the voice channel rather
    than the player bot that was leased.
    """
    channel = client.get_channel(channel_id)
    if not isinstance(channel, discord.VoiceChannel):
        raise RuntimeError(
            f"Music bot {bot_index} cannot see channel {channel_id};"
            " check the Music Bot role is allowed on it"
        )
    return channel


async def rename(guild: discord.Guild, nickname: str) -> None:
    """Give the player bot its rolled nickname. Cosmetic, never fatal."""
    try:
        await guild.me.edit(nick=nickname)
    except discord.HTTPException as exc:
        logger.warning("Music: could not rename player bot: {}", exc)
