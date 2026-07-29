"""The ephemeral play-history view: what already played, and queue it again.

Ten entries, one numbered button each, which is two rows of buttons and lines
up with the numbered list above them. The website shows the whole kept list
instead - a panel that scrolled would cost an edit per page for something
nobody is watching, and ten is what a listener means by "recently played".

Opening the view is read-only, so anyone who can see the channel may look.
Queueing is not, which is why the buttons are `GuardedButton`s: the same
in-channel check every other control runs.
"""

from __future__ import annotations

from typing import Any

import discord

from music.history import PlayedTrack
from music.models import Track
from music.queue import QueueFullError
from music.views.buttons import GuardedButton
from music.views.context import PanelContext
from music.views.format import history_line, truncate
from music.views.layout_helpers import follow_up, status_layout

SHOWN = 10
ROW_SIZE = 5
VIEW_TIMEOUT_SECONDS = 180


class HistoryView(discord.ui.LayoutView):
    """The recently played tracks, each with a button that queues it again."""

    def __init__(self, context: PanelContext, entries: list[PlayedTrack]) -> None:
        super().__init__(timeout=VIEW_TIMEOUT_SECONDS)
        self.context = context
        self._entries = entries[:SHOWN]
        self.add_item(discord.ui.Container(*self._container_items()))

    def _container_items(self) -> list[discord.ui.Item[Any]]:
        items: list[discord.ui.Item[Any]] = [
            discord.ui.TextDisplay(self._render()),
            discord.ui.Separator(),
        ]
        items.extend(self._button_rows())
        return items

    def _render(self) -> str:
        lines = ["### Recently played", "-# Press a number to queue it again."]
        lines += [
            history_line(number, entry)
            for number, entry in enumerate(self._entries, start=1)
        ]
        return "\n".join(lines)

    def _button_rows(self) -> list[discord.ui.ActionRow[Any]]:
        buttons = [
            self._button(number, entry)
            for number, entry in enumerate(self._entries, start=1)
        ]
        return [
            discord.ui.ActionRow(*buttons[start : start + ROW_SIZE])
            for start in range(0, len(buttons), ROW_SIZE)
        ]

    def _button(self, number: int, entry: PlayedTrack) -> GuardedButton:
        async def requeue(interaction: discord.Interaction) -> None:
            await self._requeue(interaction, entry.track)

        return GuardedButton(self.context, requeue, label=str(number))

    async def _requeue(self, interaction: discord.Interaction, track: Track) -> None:
        """Queue a played track again, credited to whoever pressed the button.

        The stored track carries metadata only, so this is the same path a
        saved playlist row takes: the audio is looked up when it reaches the
        front of the queue rather than being replayed from a stale handle.
        """
        await interaction.response.defer(ephemeral=True, thinking=True)
        # The name goes with the id: keeping it would credit the new request to
        # whoever asked for it the first time.
        again = track.model_copy(
            update={"requester_id": interaction.user.id, "requester_name": ""}
        )
        try:
            await self.context.session.enqueue(
                [again], actor_id=interaction.user.id, label=again.title
            )
        except QueueFullError as exc:
            await follow_up(interaction, str(exc))
            return
        await follow_up(interaction, f"Queued **{truncate(again.title)}** again.")


async def send_history(interaction: discord.Interaction, context: PanelContext) -> None:
    """Open the history view for whoever pressed the button."""
    entries = await context.session.history.recent(SHOWN)
    if not entries:
        await interaction.response.send_message(
            view=status_layout("Nothing has finished playing yet."), ephemeral=True
        )
        return
    await interaction.response.send_message(
        view=HistoryView(context, entries), ephemeral=True
    )
