"""Commands that start or interrupt playback."""

from __future__ import annotations

from typing import Any

import discord
from discord import app_commands

from music.commands.resolver import context_for, existing_session, open_session
from music.queue import QueueFullError
from music.resolve import SOURCE_PREFIXES, NoResultsError, SearchResult
from music.service import MusicService
from music.views.format import truncate
from music.views.layout_helpers import follow_up
from music.views.modals import parse_timestamp
from music.views.picker import SearchPicker

SOURCE_CHOICES = [
    app_commands.Choice(name=source.capitalize(), value=source)
    for source in SOURCE_PREFIXES
]


def make_play_command(service: MusicService) -> app_commands.Command[Any, Any, Any]:
    """`/play` - queue something, starting a session if there is none."""

    @app_commands.command(name="play", description="Play a track, playlist or URL")
    @app_commands.describe(
        query="A search term, or a Spotify, YouTube or SoundCloud link",
        source="Where to search. Ignored when the query is a link",
    )
    @app_commands.choices(source=SOURCE_CHOICES)
    async def play(
        interaction: discord.Interaction,
        query: str,
        source: app_commands.Choice[str] | None = None,
    ) -> None:
        # Searching and connecting both take longer than the three seconds
        # Discord allows before an interaction expires.
        await interaction.response.defer(ephemeral=True, thinking=True)
        session = await open_session(interaction, service)
        if session is None:
            return

        try:
            result = await session.search(
                query,
                requester_id=interaction.user.id,
                source=source.value if source else None,
            )
        except NoResultsError:
            await follow_up(interaction, f"Nothing found for **{truncate(query)}**.")
            return

        if result.needs_choice:
            # A search returns alternatives. Queueing all of them was never what
            # anyone asked for, so the caller picks and nothing is queued yet.
            await interaction.followup.send(
                view=SearchPicker(context_for(service, session), query, result.tracks),
                ephemeral=True,
            )
            return

        try:
            await session.enqueue(
                result.tracks, actor_id=interaction.user.id, label=result.label
            )
        except QueueFullError as exc:
            await follow_up(interaction, str(exc))
            return

        await follow_up(interaction, _queued_message(result))

    return play


def make_pause_command(service: MusicService) -> app_commands.Command[Any, Any, Any]:
    @app_commands.command(name="pause", description="Pause playback")
    async def pause(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        session = await existing_session(interaction, service)
        if session is None:
            return
        await session.pause(interaction.user.id, True)
        await follow_up(interaction, "Paused.")

    return pause


def make_resume_command(service: MusicService) -> app_commands.Command[Any, Any, Any]:
    @app_commands.command(name="resume", description="Resume playback")
    async def resume(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        session = await existing_session(interaction, service)
        if session is None:
            return
        await session.pause(interaction.user.id, False)
        await follow_up(interaction, "Resumed.")

    return resume


def make_skip_command(service: MusicService) -> app_commands.Command[Any, Any, Any]:
    @app_commands.command(name="skip", description="Skip the current track")
    async def skip(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        session = await existing_session(interaction, service)
        if session is None:
            return
        track = await session.skip(interaction.user.id)
        if track is None:
            await follow_up(interaction, "Skipped. Nothing left in the queue.")
            return
        await follow_up(interaction, f"Now playing **{truncate(track.title)}**.")

    return skip


def make_stop_command(service: MusicService) -> app_commands.Command[Any, Any, Any]:
    @app_commands.command(name="stop", description="Stop playback and clear the queue")
    async def stop(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        session = await existing_session(interaction, service)
        if session is None:
            return
        await session.stop(interaction.user.id)
        await follow_up(interaction, "Stopped and cleared the queue.")

    return stop


def make_seek_command(service: MusicService) -> app_commands.Command[Any, Any, Any]:
    @app_commands.command(name="seek", description="Jump to a position in the track")
    @app_commands.describe(position="mm:ss, or a number of seconds")
    async def seek(interaction: discord.Interaction, position: str) -> None:
        milliseconds = parse_timestamp(position)
        if milliseconds is None:
            await interaction.response.send_message(
                view=_bad_timestamp(), ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        session = await existing_session(interaction, service)
        if session is None:
            return
        await session.seek(interaction.user.id, milliseconds)
        await follow_up(interaction, f"Seeked to {position}.")

    return seek


def _bad_timestamp() -> discord.ui.LayoutView:
    from music.views.layout_helpers import status_layout

    return status_layout("Use `mm:ss`, for example `1:30`, or a number of seconds.")


def _queued_message(result: SearchResult) -> str:
    if result.playlist:
        return (
            f"Queued **{len(result.tracks)}** tracks"
            f" from **{truncate(result.playlist)}**."
        )
    return f"Queued **{truncate(result.tracks[0].title)}**."
