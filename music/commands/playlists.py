"""The saved-playlist command."""

from __future__ import annotations

from typing import Any

import discord
from discord import app_commands

from music.commands.resolver import context_for, open_session
from music.service import MusicService
from music.views.playlist_view import send_playlists


def make_playlist_command(service: MusicService) -> app_commands.Command[Any, Any, Any]:
    """`/playlist` - open your saved playlists and queue one.

    It opens the same view the panel's Playlists button opens, so the two
    surfaces cannot drift. A session is started first if there is none, which
    makes this a way to start playback rather than only to add to it.
    """

    @app_commands.command(name="playlist", description="Load one of your playlists")
    async def playlist(interaction: discord.Interaction) -> None:
        # Connecting a bot and then reading the playlists are both slower than
        # the three seconds Discord allows before the interaction expires.
        await interaction.response.defer(ephemeral=True, thinking=True)
        session = await open_session(interaction, service)
        if session is None:
            return
        await send_playlists(interaction, context_for(service, session))

    return playlist
