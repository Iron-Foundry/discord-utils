"""The history view and its line rendering, built without Discord or Valkey."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import discord

from music.history import PLAYED, SKIPPED, PlayedTrack
from music.views.context import PanelContext
from music.views.format import history_line
from music.views.history_view import ROW_SIZE, SHOWN, HistoryView
from tests.factories import make_track


async def _allow_everyone(user_id: int) -> bool:
    return True


def context() -> PanelContext:
    return PanelContext(session=None, guard=_allow_everyone)  # type: ignore[arg-type]


def entry(index: int, event: str = PLAYED) -> PlayedTrack:
    return PlayedTrack(
        at=datetime.now(UTC),
        event=event,
        track=make_track(identifier=f"t{index}", title=f"Track {index}"),
    )


def test_a_line_names_the_track_its_length_and_when_it_played() -> None:
    line = history_line(1, entry(0))

    assert "Track 0" in line
    assert "3:00" in line
    # A Discord relative stamp, so the client ages it without a view rebuild.
    assert ":R>" in line


def test_a_skipped_track_says_so_and_a_finished_one_does_not() -> None:
    assert "skipped" in history_line(1, entry(0, SKIPPED))
    assert "skipped" not in history_line(1, entry(0, PLAYED))


def test_a_long_title_is_truncated_rather_than_wrapping_the_row() -> None:
    long_entry = PlayedTrack(
        at=datetime.now(UTC), event=PLAYED, track=make_track(title="A" * 200)
    )

    assert "…" in history_line(1, long_entry)


def test_every_entry_gets_a_numbered_button() -> None:
    view = HistoryView(context(), [entry(index) for index in range(3)])

    assert _labels(view) == ["1", "2", "3"]


def test_ten_entries_fill_two_rows_rather_than_overflowing_one() -> None:
    view = HistoryView(context(), [entry(index) for index in range(SHOWN)])

    assert _labels(view) == [str(number) for number in range(1, SHOWN + 1)]
    assert len(_rows(view)) == SHOWN // ROW_SIZE


def test_the_view_shows_no_more_than_the_panel_budget_allows() -> None:
    # The website shows the whole kept list; the panel deliberately does not.
    view = HistoryView(context(), [entry(index) for index in range(SHOWN * 3)])

    assert len(_labels(view)) == SHOWN


def test_the_numbers_in_the_list_match_the_numbers_on_the_buttons() -> None:
    view = HistoryView(context(), [entry(index) for index in range(3)])
    rendered = view._render()

    for number, label in enumerate(_labels(view), start=1):
        assert label == str(number)
        assert f"Track {number - 1}" in rendered


def _rows(view: HistoryView) -> list[discord.ui.ActionRow[Any]]:
    container = view.children[0]
    return [
        item
        for item in container.children  # type: ignore[attr-defined]
        if isinstance(item, discord.ui.ActionRow)
    ]


def _labels(view: HistoryView) -> list[str]:
    return [
        button.label
        for row in _rows(view)
        for button in row.children
        if isinstance(button, discord.ui.Button) and button.label is not None
    ]
