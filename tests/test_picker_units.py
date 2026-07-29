"""When a search offers a choice, and what the picker shows.

The regression this covers: a plain search returns many results and every one
of them used to land in the queue.
"""

from __future__ import annotations

from typing import Any, cast

import discord

from music.resolve import SearchResult
from music.views.context import PanelContext
from music.views.picker import (
    RESULTS_SHOWN,
    SearchPicker,
    _describe,
    _label,
)
from tests.factories import make_track


async def _allow_everyone(user_id: int) -> bool:
    return True


def context() -> PanelContext:
    return PanelContext(session=cast(Any, None), guard=_allow_everyone)


def results(count: int) -> list[Any]:
    return [
        make_track(identifier=f"t{i}", title=f"Nightcall {i}", length=200_000 + i)
        for i in range(count)
    ]


def test_a_search_with_alternatives_asks_the_user() -> None:
    assert SearchResult(tracks=results(8)).needs_choice


def test_a_single_result_is_queued_without_asking() -> None:
    # A link resolves to exactly one track, so there is nothing to choose.
    assert not SearchResult(tracks=results(1)).needs_choice


def test_a_playlist_is_never_a_choice() -> None:
    # Asking which of a playlist's 60 tracks to keep would be absurd.
    assert not SearchResult(
        tracks=results(60), playlist="Barbarian Anthems"
    ).needs_choice


def test_label_prefers_the_playlist_name() -> None:
    assert SearchResult(tracks=results(3), playlist="Anthems").label == "Anthems"
    assert SearchResult(tracks=results(1)).label == "Nightcall 0"


def test_picker_shows_the_results_it_was_given() -> None:
    picker = SearchPicker(context(), "nightcall", results(5))
    select = _select_of(picker)

    assert len(select["options"]) == 5
    assert select["options"][0]["label"] == "Nightcall 0"


def test_picker_caps_a_long_result_set() -> None:
    picker = SearchPicker(context(), "nightcall", results(40))
    assert len(_select_of(picker)["options"]) == RESULTS_SHOWN
    assert RESULTS_SHOWN <= 25


def test_picker_lets_several_results_be_queued_at_once() -> None:
    select = _select_of(SearchPicker(context(), "nightcall", results(6)))
    assert select["min_values"] == 1
    assert select["max_values"] == 6


def test_every_option_carries_the_detail_that_separates_a_cover() -> None:
    track = make_track(title="Nightcall", author="Kavinsky", length=258_000)
    description = _describe(track)

    assert "Kavinsky" in description
    assert "4:18" in description
    assert "spotify" in description


def test_the_listing_repeats_the_detail_in_full() -> None:
    picker = SearchPicker(context(), "nightcall", results(3))
    body = _text_of(picker)

    assert "Nightcall 0" in body
    assert "3 found" in body
    assert "Nothing is queued until you pick" in body


def test_option_text_stays_inside_the_discord_limits() -> None:
    long_track = make_track(title="A" * 400, author="B" * 400)
    picker = SearchPicker(context(), "x" * 300, [long_track])
    select = _select_of(picker)

    assert len(select["options"][0]["label"]) <= 100
    assert len(select["options"][0]["description"]) <= 100


def test_picker_stays_inside_the_component_budget() -> None:
    picker = SearchPicker(context(), "nightcall", results(RESULTS_SHOWN))
    assert picker._total_children <= 40
    assert picker.content_length() <= 4000


def test_label_summarises_a_multi_pick() -> None:
    assert _label(results(1)) == "Nightcall 0"
    assert _label(results(3)) == "3 tracks"


def _select_of(picker: SearchPicker) -> dict[str, Any]:
    return next(
        component
        for row in picker.to_components()[0]["components"]
        if row["type"] == 1
        for component in row["components"]
        if component["type"] == 3
    )


def _text_of(view: discord.ui.LayoutView) -> str:
    return "\n".join(
        item.content
        for item in view.walk_children()
        if isinstance(item, discord.ui.TextDisplay)
    )
