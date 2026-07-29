"""The panel view: budget, rendering and control state.

The view is built from a snapshot, so all of this runs without Discord, without
Lavalink and without Valkey.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from music.models import LoopMode
from music.playlists import PlaylistClient
from music.views.context import PanelContext
from music.views.format import duration, now_playing, status_line, truncate, up_next
from music.views.modals import parse_timestamp
from music.views.panel_view import MAX_CHARACTERS, MAX_COMPONENTS, MusicPanel
from music.views.snapshot import JUMP_OPTIONS, PanelSnapshot
from tests.factories import make_track


async def _allow_everyone(user_id: int) -> bool:
    return True


def context(*, with_playlists: bool = False) -> PanelContext:
    client = PlaylistClient("http://api.invalid", "key") if with_playlists else None
    return PanelContext(
        session=None,  # type: ignore[arg-type]
        guard=_allow_everyone,
        playlists=client,
    )


def full_snapshot() -> PanelSnapshot:
    """The largest panel the design can produce: long titles, a full select."""
    long_title = "A" * 200
    current = make_track(title=long_title, author="B" * 200)
    current.played_source = "youtube"
    return PanelSnapshot(
        voice_channel_id=1,
        current=current,
        queue_head=[
            make_track(identifier=f"t{i}", title=long_title, author="C" * 120)
            for i in range(JUMP_OPTIONS)
        ],
        queue_length=500,
        remaining_ms=99 * 3600 * 1000,
        volume=150,
        loop=LoopMode.QUEUE,
        ends_at=datetime.now(UTC) + timedelta(minutes=3),
    )


def test_panel_stays_inside_the_component_budget() -> None:
    panel = MusicPanel(context(), full_snapshot())
    assert panel._total_children <= MAX_COMPONENTS


def test_panel_stays_inside_the_character_budget() -> None:
    panel = MusicPanel(context(), full_snapshot())
    assert panel.content_length() <= MAX_CHARACTERS


def test_panel_carries_no_content_or_embeds() -> None:
    # Both stop working under the components-v2 flag, and the flag cannot be
    # removed from a message once sent.
    panel = MusicPanel(context(), full_snapshot())
    assert not hasattr(panel, "content")
    assert panel.to_components()[0]["type"] == 17


def test_idle_panel_renders_and_disables_transport() -> None:
    panel = MusicPanel(context(), PanelSnapshot(voice_channel_id=1))
    rows = [c for c in panel.to_components()[0]["components"] if c["type"] == 1]
    transport = rows[0]["components"]

    assert [button["disabled"] for button in transport[:3]] == [True, True, True]


def test_idle_panel_has_no_jump_select() -> None:
    panel = MusicPanel(context(), PanelSnapshot(voice_channel_id=1))
    selects = [
        component
        for row in panel.to_components()[0]["components"]
        if row["type"] == 1
        for component in row["components"]
        if component["type"] == 3
    ]
    assert selects == []


def test_jump_select_offers_at_most_the_discord_maximum() -> None:
    panel = MusicPanel(context(), full_snapshot())
    options = [
        component["options"]
        for row in panel.to_components()[0]["components"]
        if row["type"] == 1
        for component in row["components"]
        if component["type"] == 3
    ]
    assert len(options[0]) == JUMP_OPTIONS <= 25


def test_no_playlists_button_when_playlists_are_not_configured() -> None:
    # No control at all beats a button that errors when it is pressed.
    panel = MusicPanel(context(), full_snapshot())
    assert "Playlists" not in _labels(panel)


def test_the_playlists_button_appears_once_the_api_is_configured() -> None:
    panel = MusicPanel(context(with_playlists=True), full_snapshot())
    assert "Playlists" in _labels(panel)


def test_the_panel_still_fits_its_budget_with_the_playlists_row() -> None:
    panel = MusicPanel(context(with_playlists=True), full_snapshot())
    assert panel._total_children <= MAX_COMPONENTS
    assert panel.content_length() <= MAX_CHARACTERS


def _labels(panel: MusicPanel) -> set[str]:
    return {
        component.get("label", "")
        for row in panel.to_components()[0]["components"]
        if row["type"] == 1
        for component in row["components"]
    }


def test_accent_follows_the_source_that_actually_played() -> None:
    panel = MusicPanel(context(), full_snapshot())
    # YouTube red, because the Spotify request was mirrored to YouTube.
    assert panel.to_components()[0]["accent_color"] == 0xFF0000


@pytest.mark.parametrize(
    ("milliseconds", "expected"),
    [(0, "0:00"), (7000, "0:07"), (247_000, "4:07"), (3_753_000, "1:02:33")],
)
def test_duration_formatting(milliseconds: int, expected: str) -> None:
    assert duration(milliseconds) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [("1:30", 90_000), ("0:07", 7000), ("90", 90_000), ("", None), ("1:99", None)],
)
def test_timestamp_parsing(text: str, expected: int | None) -> None:
    assert parse_timestamp(text) == expected


def test_now_playing_shows_the_mirror_when_it_differs() -> None:
    track = make_track()
    track.played_source = "youtube"
    text = now_playing(PanelSnapshot(voice_channel_id=1, current=track))

    assert "spotify → youtube" in text


def test_now_playing_shows_one_source_when_nothing_was_mirrored() -> None:
    track = make_track(source="youtube")
    track.played_source = "youtube"
    text = now_playing(PanelSnapshot(voice_channel_id=1, current=track))

    assert "→" not in text


def test_remaining_time_is_a_relative_timestamp_not_a_countdown() -> None:
    # The viewer's client ages it, so the panel never needs a timer.
    ends = datetime.now(UTC) + timedelta(minutes=3)
    text = now_playing(
        PanelSnapshot(voice_channel_id=1, current=make_track(), ends_at=ends)
    )
    assert f"<t:{int(ends.timestamp())}:R>" in text


def test_a_stream_reports_no_end_time() -> None:
    track = make_track()
    track.is_stream = True
    text = now_playing(PanelSnapshot(voice_channel_id=1, current=track))

    assert "Live stream" in text
    assert ":R>" not in text


def test_up_next_summarises_the_rest_of_the_queue() -> None:
    snapshot = PanelSnapshot(
        voice_channel_id=1,
        queue_head=[make_track(identifier=f"t{i}", length=60_000) for i in range(5)],
        queue_length=12,
        remaining_ms=2_840_000,
    )
    text = up_next(snapshot)

    assert text.count("\n") == 3  # three tracks named, then the summary
    assert "12 tracks" in text
    assert "47:20 remaining" in text


def test_up_next_when_nothing_is_queued() -> None:
    assert "Nothing queued" in up_next(PanelSnapshot(voice_channel_id=1))


def test_status_line_reports_every_mode_in_force() -> None:
    snapshot = PanelSnapshot(voice_channel_id=1, loop=LoopMode.TRACK, volume=60)
    assert status_line(snapshot) == "-# Loop track · Shuffle off · Volume 60%"


def test_status_line_shows_shuffle_when_it_is_on() -> None:
    snapshot = PanelSnapshot(voice_channel_id=1, volume=60, shuffle=True)
    assert "Shuffle on" in status_line(snapshot)


def test_truncate_keeps_long_titles_inside_the_limit() -> None:
    assert len(truncate("x" * 500, 80)) == 80
