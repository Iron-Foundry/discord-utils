"""The ephemeral full-queue view: paginate, remove, move.

Ephemeral and per-user, so it never competes with the panel for edit budget and
several people can page through the queue at once without seeing each other's
position in it.
"""

from __future__ import annotations

from typing import Any

import discord

from music.models import Track
from music.views.buttons import CallbackButton
from music.views.context import PanelContext
from music.views.format import duration, truncate
from music.views.layout_helpers import status_layout
from music.views.modals import MoveModal

PAGE_SIZE = 10
VIEW_TIMEOUT_SECONDS = 180


class QueueView(discord.ui.LayoutView):
    """One page of the queue, with the controls to edit it."""

    def __init__(
        self, context: PanelContext, tracks: list[Track], page: int = 0
    ) -> None:
        super().__init__(timeout=VIEW_TIMEOUT_SECONDS)
        self.context = context
        self._tracks = tracks
        self._pages = max(1, -(-len(tracks) // PAGE_SIZE))
        self._page = max(0, min(self._pages - 1, page))
        self.add_item(discord.ui.Container(*self._children_for_page()))

    def _children_for_page(self) -> list[discord.ui.Item[Any]]:
        items: list[discord.ui.Item[Any]] = [
            discord.ui.TextDisplay(self._render()),
            discord.ui.Separator(),
            self._pager(),
        ]
        page_tracks = self._page_tracks()
        if page_tracks:
            items.append(discord.ui.ActionRow(RemoveSelect(self, page_tracks)))
        return items

    def _page_tracks(self) -> list[tuple[int, Track]]:
        start = self._page * PAGE_SIZE
        return list(enumerate(self._tracks[start : start + PAGE_SIZE], start=start))

    def _render(self) -> str:
        if not self._tracks:
            return "### Queue\nNothing queued."
        lines = [f"### Queue · page {self._page + 1}/{self._pages}"]
        lines += [
            f"`{index + 1:>3}` {truncate(track.title, 60)} · -# {duration(track.length_ms)}"
            for index, track in self._page_tracks()
        ]
        return "\n".join(lines)

    def _pager(self) -> discord.ui.ActionRow[Any]:
        async def previous(interaction: discord.Interaction) -> None:
            await self._turn(interaction, self._page - 1)

        async def nxt(interaction: discord.Interaction) -> None:
            await self._turn(interaction, self._page + 1)

        async def move(interaction: discord.Interaction) -> None:
            if not await self.context.allows(interaction):
                return
            await interaction.response.send_modal(MoveModal(self.context))

        return discord.ui.ActionRow(
            CallbackButton(previous, emoji="◀️", disabled=self._page == 0),
            CallbackButton(nxt, emoji="▶️", disabled=self._page >= self._pages - 1),
            CallbackButton(move, label="Move", disabled=len(self._tracks) < 2),
        )

    async def _turn(self, interaction: discord.Interaction, page: int) -> None:
        tracks = await self.context.session.queue.all()
        await interaction.response.edit_message(
            view=QueueView(self.context, tracks, page)
        )

    async def refresh(self, interaction: discord.Interaction) -> None:
        """Rebuild from Valkey after an edit, staying on the same page."""
        tracks = await self.context.session.queue.all()
        await interaction.response.edit_message(
            view=QueueView(self.context, tracks, self._page)
        )


class RemoveSelect(discord.ui.Select[Any]):
    """Drop one track from the page currently shown."""

    def __init__(self, view: QueueView, page_tracks: list[tuple[int, Track]]) -> None:
        super().__init__(
            placeholder="Remove a track",
            options=[
                discord.SelectOption(
                    label=truncate(track.title, 88),
                    description=f"#{index + 1}",
                    value=str(index),
                )
                for index, track in page_tracks
            ],
        )
        self._queue_view = view

    async def callback(self, interaction: discord.Interaction) -> None:
        context = self._queue_view.context
        if not await context.allows(interaction):
            return
        await context.session.remove(interaction.user.id, int(self.values[0]))
        await self._queue_view.refresh(interaction)


async def send_queue(interaction: discord.Interaction, context: PanelContext) -> None:
    """Open the queue view for whoever pressed the button."""
    tracks = await context.session.queue.all()
    if not tracks:
        await interaction.response.send_message(
            view=status_layout("Nothing queued."), ephemeral=True
        )
        return
    await interaction.response.send_message(
        view=QueueView(context, tracks), ephemeral=True
    )
