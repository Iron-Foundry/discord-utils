"""Gateway events the music service reacts to, on the orchestrator client.

The orchestrator watches voice state rather than the player bots, because it is
the client with the member cache and it already sees every channel. Two things
depend on it: the roster that decides who may control a session, and teardown
when the last listener leaves.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from loguru import logger

from music.notify import publish_state
from music.voice import VoiceRoster, human_ids, is_deserted

if TYPE_CHECKING:
    from core.discord_client import DiscordClient
    from music.service import MusicService


def register(service: MusicService, client: DiscordClient) -> None:
    """Attach the music service's voice and channel listeners."""

    async def refresh(channel: discord.VoiceChannel) -> None:
        session = service.session(channel.id)
        if session is None:
            return
        await VoiceRoster(service.valkey, channel.id).sync(human_ids(channel))
        if is_deserted(channel):
            logger.info("Music: channel {} is empty, ending session", channel.id)
            await service.leave(channel.id)
            return
        # Who is in the channel is who may control it, so a join or a leave has
        # to reach the web the same way a track change does. Without this the
        # website keeps whatever answer it got when the page was opened, and
        # someone who joins after that stays locked out of their own session.
        await publish_state(service.valkey, session)

    async def on_voice_state_update(
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.bot:
            return
        for channel in (before.channel, after.channel):
            if isinstance(channel, discord.VoiceChannel):
                await refresh(channel)

    async def on_guild_channel_delete(channel: discord.abc.GuildChannel) -> None:
        # Temp VCs are deleted out from under a session when they empty, so the
        # session has to end on the delete itself, not on a voice state that
        # will never arrive for a channel that no longer exists.
        if service.session(channel.id) is not None:
            logger.info("Music: channel {} was deleted, ending session", channel.id)
            await service.leave(channel.id)

    client.add_listener(on_voice_state_update, "on_voice_state_update")
    client.add_listener(on_guild_channel_delete, "on_guild_channel_delete")
