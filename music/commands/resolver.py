"""Getting from an interaction to the session it is allowed to act on.

Every music command starts here. The voice channel is taken from the caller's
own voice state rather than from an argument, which makes the authorisation
question answer itself: if the command resolved a channel at all, the caller is
standing in it, and being in the channel is exactly what control authority
means.
"""

from __future__ import annotations

import discord

from music.models import PoolExhaustedError
from music.service import MusicService
from music.session import MusicSession
from music.views.context import PanelContext
from music.views.layout_helpers import follow_up
from music.voice import VoiceRoster

NOT_IN_VOICE = "Join a voice channel first."
NOTHING_PLAYING = "Nothing is playing in your channel."


def caller_channel(interaction: discord.Interaction) -> discord.VoiceChannel | None:
    """The voice channel the caller is connected to, if it is a normal one."""
    member = interaction.user
    if not isinstance(member, discord.Member) or member.voice is None:
        return None
    channel = member.voice.channel
    return channel if isinstance(channel, discord.VoiceChannel) else None


async def existing_session(
    interaction: discord.Interaction, service: MusicService
) -> MusicSession | None:
    """The session in the caller's channel. Answers the interaction if there is none."""
    channel = caller_channel(interaction)
    if channel is None:
        await follow_up(interaction, NOT_IN_VOICE)
        return None

    session = service.session(channel.id)
    if session is None:
        await follow_up(interaction, NOTHING_PLAYING)
        return None
    return session


async def open_session(
    interaction: discord.Interaction, service: MusicService
) -> MusicSession | None:
    """The session in the caller's channel, starting one if there is none."""
    channel = caller_channel(interaction)
    if channel is None:
        await follow_up(interaction, NOT_IN_VOICE)
        return None

    session = service.session(channel.id)
    if session is not None:
        return session

    try:
        return await service.join(channel)
    except PoolExhaustedError as exc:
        await follow_up(interaction, f"Every music bot is busy. {exc}")
    except RuntimeError as exc:
        await follow_up(interaction, str(exc))
    return None


def context_for(service: MusicService, session: MusicSession) -> PanelContext:
    """A panel context for the views a command opens, sharing the panel's guard."""
    roster = VoiceRoster(service.valkey, session.voice_channel_id)
    return PanelContext(
        session=session, guard=roster.may_control, playlists=service.playlists
    )
