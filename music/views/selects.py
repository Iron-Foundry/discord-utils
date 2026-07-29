"""The jump-to-track select.

Discord caps a select at 25 options, so this offers the head of the queue only.
A longer queue is reached through the ephemeral queue view, which paginates.

The playlist select the design sketches belongs to Stage 6, where playlists
first exist. Adding it now would mean a control with nothing behind it.
"""

from __future__ import annotations

from typing import Any

import discord

from music.views.context import PanelContext
from music.views.format import duration, truncate
from music.views.layout_helpers import follow_up
from music.views.snapshot import PanelSnapshot

OPTION_LABEL_LIMIT = 100


class JumpSelect(discord.ui.Select[Any]):
    """Jump ahead in the queue, discarding everything skipped over."""

    def __init__(self, context: PanelContext, snapshot: PanelSnapshot) -> None:
        super().__init__(
            placeholder="Jump to a track in the queue",
            options=[
                discord.SelectOption(
                    label=truncate(track.title, OPTION_LABEL_LIMIT - 12),
                    description=f"{track.author[:40]} · {duration(track.length_ms)}",
                    value=str(index),
                )
                for index, track in enumerate(snapshot.queue_head)
            ],
        )
        self._context = context

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await self._context.allows(interaction):
            return
        await interaction.response.defer()
        track = await self._context.session.jump(
            interaction.user.id, int(self.values[0])
        )
        if track is None:
            await follow_up(interaction, "That track is no longer in the queue.")


def jump_row(
    context: PanelContext, snapshot: PanelSnapshot
) -> discord.ui.ActionRow[Any] | None:
    """The select row, or nothing at all when the queue is empty."""
    if not snapshot.queue_head:
        return None
    return discord.ui.ActionRow(JumpSelect(context, snapshot))
