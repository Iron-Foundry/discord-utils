"""Choosing a saved playlist to queue.

Per-viewer and ephemeral rather than a select baked into the panel. The panel is
a single shared message, so a select on it could only ever offer the public
playlists - everyone's own would be unreachable from the panel entirely.
Opening the list per viewer means each person sees exactly what they may load,
and a render never spends an HTTP round trip on a control most renders would
not use.
"""

from __future__ import annotations

from typing import Any

import discord

from music.playlists import PLAYLISTS_SHOWN, PlaylistError, PlaylistSummary, to_tracks
from music.queue import QueueFullError
from music.views.context import PanelContext
from music.views.format import (
    playlist_heading,
    playlist_option,
    playlist_queued,
    truncate,
)
from music.views.layout_helpers import follow_up, status_layout

VIEW_TIMEOUT_SECONDS = 120
LABEL_LIMIT = 100
DESCRIPTION_LIMIT = 100

NO_PLAYLISTS = (
    "You have no saved playlists, and none are shared."
    " Playlists are created on the website."
)
UNAVAILABLE = "Playlists are not available on this server."
EMPTY_PLAYLIST = "That playlist has no tracks in it."


class PlaylistPicker(discord.ui.LayoutView):
    """The playlists this viewer may load, and the control that queues one."""

    def __init__(self, context: PanelContext, playlists: list[PlaylistSummary]) -> None:
        super().__init__(timeout=VIEW_TIMEOUT_SECONDS)
        self.context = context
        self.playlists = playlists[:PLAYLISTS_SHOWN]
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(playlist_heading(len(self.playlists))),
                discord.ui.Separator(),
                discord.ui.ActionRow(PlaylistSelect(self)),
            )
        )


class PlaylistSelect(discord.ui.Select[Any]):
    """Queue a saved playlist, resolving its tracks only as they play."""

    def __init__(self, picker: PlaylistPicker) -> None:
        super().__init__(
            placeholder="Load a playlist",
            options=[
                discord.SelectOption(
                    label=truncate(playlist.name, LABEL_LIMIT),
                    description=truncate(playlist_option(playlist), DESCRIPTION_LIMIT),
                    value=str(playlist.id),
                )
                for playlist in picker.playlists
            ],
        )
        self._picker = picker

    async def callback(self, interaction: discord.Interaction) -> None:
        context = self._picker.context
        if not await context.allows(interaction):
            return
        # Fetching the tracks and queueing them both outlast the three seconds
        # Discord allows before an interaction expires.
        await interaction.response.defer()

        client = context.playlists
        if client is None:
            await _replace(interaction, UNAVAILABLE)
            return

        try:
            playlist = await client.detail(interaction.user.id, int(self.values[0]))
        except PlaylistError as exc:
            await _replace(interaction, str(exc))
            return

        tracks = to_tracks(playlist, requester_id=interaction.user.id)
        if not tracks:
            await _replace(interaction, EMPTY_PLAYLIST)
            return

        try:
            await context.session.enqueue(
                tracks, actor_id=interaction.user.id, label=playlist.name
            )
        except QueueFullError as exc:
            await _replace(interaction, str(exc))
            return

        self._picker.stop()
        await _replace(interaction, playlist_queued(playlist.name, tracks))


async def send_playlists(
    interaction: discord.Interaction, context: PanelContext
) -> None:
    """Open the playlist list for whoever asked for it.

    The interaction must already be deferred: reading playlists is an HTTP round
    trip to api-backend, and both callers - the panel button and `/playlist` -
    have work of their own to do before this that also outlasts the three
    seconds Discord allows.
    """
    client = context.playlists
    if client is None:
        await follow_up(interaction, UNAVAILABLE)
        return

    try:
        playlists = await client.for_user(interaction.user.id)
    except PlaylistError as exc:
        await follow_up(interaction, str(exc))
        return

    if not playlists:
        await follow_up(interaction, NO_PLAYLISTS)
        return
    await interaction.followup.send(
        view=PlaylistPicker(context, playlists), ephemeral=True
    )


async def _replace(interaction: discord.Interaction, content: str) -> None:
    """Swap the picker for a result, since the choice has been made."""
    await interaction.edit_original_response(view=status_layout(content))
