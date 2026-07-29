"""Choosing which search results to queue.

A plain search returns alternatives, and the right one is rarely the first: a
query like "nightcall" matches the original, half a dozen covers and a remix.
The results are therefore shown with enough detail to tell them apart - title,
artist, duration and source - and nothing is queued until the user says which.

Ephemeral and per-user, so one person picking never blocks anyone else, and a
picker left unanswered simply expires.
"""

from __future__ import annotations

from typing import Any

import discord

from music.models import Track
from music.views.context import PanelContext
from music.views.format import duration, truncate

RESULTS_SHOWN = 10
PICKER_TIMEOUT_SECONDS = 60

LABEL_LIMIT = 100
DESCRIPTION_LIMIT = 100


class SearchPicker(discord.ui.LayoutView):
    """Pick one or several results to queue."""

    def __init__(
        self,
        context: PanelContext,
        query: str,
        tracks: list[Track],
    ) -> None:
        super().__init__(timeout=PICKER_TIMEOUT_SECONDS)
        self.context = context
        self.tracks = tracks[:RESULTS_SHOWN]
        self.chosen: list[Track] = []
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(_heading(query, len(self.tracks))),
                discord.ui.TextDisplay(_listing(self.tracks)),
                discord.ui.Separator(),
                discord.ui.ActionRow(ResultSelect(self)),
            )
        )


class ResultSelect(discord.ui.Select[Any]):
    """The results, described well enough to tell covers apart from originals."""

    def __init__(self, picker: SearchPicker) -> None:
        super().__init__(
            placeholder="Pick what to queue",
            min_values=1,
            # Several results can be queued at once: picking three covers in
            # one go beats running the same search three times.
            max_values=len(picker.tracks),
            options=[
                discord.SelectOption(
                    label=truncate(track.title, LABEL_LIMIT),
                    description=truncate(_describe(track), DESCRIPTION_LIMIT),
                    value=str(index),
                )
                for index, track in enumerate(picker.tracks)
            ],
        )
        self._picker = picker

    async def callback(self, interaction: discord.Interaction) -> None:
        picker = self._picker
        if not await picker.context.allows(interaction):
            return

        chosen = [picker.tracks[int(value)] for value in self.values]
        picker.chosen = chosen
        picker.stop()

        await interaction.response.edit_message(
            view=_confirmation(chosen), delete_after=None
        )
        await picker.context.session.enqueue(
            chosen, actor_id=interaction.user.id, label=_label(chosen)
        )


def _describe(track: Track) -> str:
    """Artist, length and where it came from - the three things that separate
    a cover from the original."""
    return f"{track.author} · {duration(track.length_ms)} · {track.requested_source}"


def _heading(query: str, count: int) -> str:
    return (
        f"### Results for **{truncate(query, 60)}**\n"
        f"-# {count} found. Nothing is queued until you pick."
    )


def _listing(tracks: list[Track]) -> str:
    """The same results as a numbered list.

    A select option's description is short and easy to miss; the list carries
    the full detail and stays readable at ten results.
    """
    return "\n".join(
        f"`{index:>2}` **{truncate(track.title, 60)}**\n-# {_describe(track)}"
        for index, track in enumerate(tracks, start=1)
    )


def _label(tracks: list[Track]) -> str:
    if len(tracks) == 1:
        return tracks[0].title
    return f"{len(tracks)} tracks"


def _confirmation(tracks: list[Track]) -> discord.ui.LayoutView:
    from music.views.layout_helpers import status_layout

    if len(tracks) == 1:
        return status_layout(f"Queued **{truncate(tracks[0].title)}**.")
    body = "\n".join(f"-# {truncate(track.title, 60)}" for track in tracks)
    return status_layout(f"Queued **{len(tracks)}** tracks.\n{body}")
