"""Commands that inspect or reorder the queue."""

from __future__ import annotations

from typing import Any

import discord
from discord import app_commands

from music.commands.resolver import context_for, existing_session
from music.models import LoopMode
from music.service import MusicService
from music.state import MAX_VOLUME
from music.views.format import now_playing, status_line, truncate, up_next
from music.views.layout_helpers import follow_up, status_layout
from music.views.queue_view import QueueView
from music.views.snapshot import take_snapshot

LOOP_CHOICES = [
    app_commands.Choice(name="Off", value=LoopMode.OFF.value),
    app_commands.Choice(name="Track", value=LoopMode.TRACK.value),
    app_commands.Choice(name="Queue", value=LoopMode.QUEUE.value),
]


def make_queue_command(service: MusicService) -> app_commands.Command[Any, Any, Any]:
    """`/queue` - the same paginated view the panel's Queue button opens."""

    @app_commands.command(name="queue", description="Show the queue")
    async def queue(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        session = await existing_session(interaction, service)
        if session is None:
            return

        tracks = await session.queue.all()
        if not tracks:
            await follow_up(interaction, "Nothing queued.")
            return
        await interaction.followup.send(
            view=QueueView(context_for(service, session), tracks), ephemeral=True
        )

    return queue


def make_nowplaying_command(
    service: MusicService,
) -> app_commands.Command[Any, Any, Any]:
    @app_commands.command(name="nowplaying", description="Show what is playing")
    async def nowplaying(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        session = await existing_session(interaction, service)
        if session is None:
            return

        snapshot = await take_snapshot(session)
        body = "\n".join(
            (now_playing(snapshot), "", up_next(snapshot), status_line(snapshot))
        )
        await interaction.followup.send(view=status_layout(body), ephemeral=True)

    return nowplaying


def make_remove_command(service: MusicService) -> app_commands.Command[Any, Any, Any]:
    @app_commands.command(name="remove", description="Remove a track from the queue")
    @app_commands.describe(position="Its position in the queue, as /queue shows it")
    async def remove(interaction: discord.Interaction, position: int) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        session = await existing_session(interaction, service)
        if session is None:
            return

        title = await session.remove(interaction.user.id, position - 1)
        if title is None:
            await follow_up(interaction, f"No track at position {position}.")
            return
        await follow_up(interaction, f"Removed **{truncate(title)}**.")

    return remove


def make_shuffle_command(service: MusicService) -> app_commands.Command[Any, Any, Any]:
    @app_commands.command(name="shuffle", description="Turn random play on or off")
    async def shuffle(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        session = await existing_session(interaction, service)
        if session is None:
            return
        # A mode, matching the panel button: the queue keeps its order and the
        # next track is drawn at random while this is on.
        enabled = not await session.state.shuffle()
        await session.set_shuffle(interaction.user.id, enabled)
        await follow_up(interaction, f"Shuffle {'on' if enabled else 'off'}.")

    return shuffle


def make_loop_command(service: MusicService) -> app_commands.Command[Any, Any, Any]:
    @app_commands.command(name="loop", description="Set the loop mode")
    @app_commands.describe(mode="Off, repeat the track, or repeat the whole queue")
    @app_commands.choices(mode=LOOP_CHOICES)
    async def loop(
        interaction: discord.Interaction, mode: app_commands.Choice[str]
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        session = await existing_session(interaction, service)
        if session is None:
            return
        await session.set_loop(interaction.user.id, LoopMode(mode.value))
        await follow_up(interaction, f"Loop set to **{mode.name.lower()}**.")

    return loop


def make_volume_command(service: MusicService) -> app_commands.Command[Any, Any, Any]:
    @app_commands.command(name="volume", description="Set the volume")
    @app_commands.describe(percent=f"0 to {MAX_VOLUME}")
    async def volume(
        interaction: discord.Interaction,
        percent: app_commands.Range[int, 0, MAX_VOLUME],
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        session = await existing_session(interaction, service)
        if session is None:
            return
        applied = await session.set_volume(interaction.user.id, percent)
        await follow_up(interaction, f"Volume set to {applied}%.")

    return volume
