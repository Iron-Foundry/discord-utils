"""Modals opened from the panel."""

from __future__ import annotations

import re

import discord

from music.views.context import PanelContext
from music.views.layout_helpers import reply

_CLOCK = re.compile(r"^(\d+):([0-5]\d)$")


def parse_timestamp(text: str) -> int | None:
    """`1:30` or a bare `90` into milliseconds. None when it is neither.

    A bare number is seconds, so it is not bounded at 59 the way the seconds
    field of a clock time is.
    """
    text = text.strip()
    if ":" not in text:
        return int(text) * 1000 if text.isdigit() else None
    match = _CLOCK.match(text)
    if match is None:
        return None
    return ((int(match[1]) * 60) + int(match[2])) * 1000


class SeekModal(discord.ui.Modal, title="Seek"):
    """Jump to a position in the current track."""

    position: discord.ui.TextInput[discord.ui.Modal] = discord.ui.TextInput(
        label="Position",
        placeholder="1:30",
        max_length=8,
        required=True,
    )

    def __init__(self, context: PanelContext) -> None:
        super().__init__()
        self._context = context

    async def on_submit(self, interaction: discord.Interaction) -> None:
        milliseconds = parse_timestamp(self.position.value)
        if milliseconds is None:
            await reply(interaction, "Use `mm:ss`, for example `1:30`.")
            return
        await interaction.response.defer()
        await self._context.session.seek(interaction.user.id, milliseconds)


class MoveModal(discord.ui.Modal, title="Move a track"):
    """Reorder the queue by position, one-based to match what the list shows."""

    source: discord.ui.TextInput[discord.ui.Modal] = discord.ui.TextInput(
        label="Track number", placeholder="4", max_length=4, required=True
    )
    destination: discord.ui.TextInput[discord.ui.Modal] = discord.ui.TextInput(
        label="New position", placeholder="1", max_length=4, required=True
    )

    def __init__(self, context: PanelContext) -> None:
        super().__init__()
        self._context = context

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            source = int(self.source.value) - 1
            destination = int(self.destination.value) - 1
        except ValueError:
            await reply(interaction, "Both fields need to be numbers.")
            return

        title = await self._context.session.move(
            interaction.user.id, source, destination
        )
        if title is None:
            await reply(interaction, "No track at that position.")
            return
        await reply(interaction, f"Moved **{title}** to #{destination + 1}.")
