"""Reading saved playlists, and turning them into something queueable.

The HTTP layer is exercised against a transport stub rather than a live API:
what matters here is that a refusal becomes a message a user can read, and that
a saved row becomes a track the session can queue without a search per row.
"""

from __future__ import annotations

from typing import Any, cast

import httpx
import pytest

from music.playlists import (
    MISSING,
    PLAYLISTS_SHOWN,
    PlaylistClient,
    PlaylistDetail,
    PlaylistError,
    PlaylistSummary,
    to_tracks,
)
from music.service import build_playlist_client
from music.views.context import PanelContext
from music.views.format import playlist_option, playlist_queued
from music.views.playlist_view import PlaylistPicker

ROW: dict[str, Any] = {
    "source": "spotify",
    "identifier": "abc123",
    "title": "Zanaris Nocturne",
    "author": "Barbarian Assault",
    "duration_ms": 180_000,
    "isrc": "USABC1234567",
    "uri": "https://open.spotify.com/track/abc123",
    "artwork": "https://i.scdn.co/image/abc123",
    "position": 0,
}

PLAYLIST: dict[str, Any] = {
    "id": 4,
    "owner_discord_id": 99,
    "name": "Slayer Tunes",
    "is_public": False,
    "track_count": 1,
    "tracks": [ROW],
}


def client_returning(
    status: int, body: Any, *, seen: list[httpx.Request] | None = None
) -> PlaylistClient:
    """A client whose transport answers with exactly this response."""

    def handle(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, json=body)

    return PlaylistClient(
        "http://api.invalid", "shhh", transport=httpx.MockTransport(handle)
    )


async def test_a_list_comes_back_as_summaries() -> None:
    client = client_returning(200, [dict(PLAYLIST)])
    playlists = await client.for_user(99)

    assert [p.name for p in playlists] == ["Slayer Tunes"]
    assert playlists[0].track_count == 1


async def test_the_service_key_is_sent_as_the_verification_header() -> None:
    seen: list[httpx.Request] = []
    client = client_returning(200, [], seen=seen)
    await client.for_user(99)

    assert seen[0].headers["verification-code"] == "shhh"
    assert seen[0].url.path == "/music/bot/99/playlists"


async def test_a_playlist_that_is_not_visible_reads_as_missing() -> None:
    # api-backend answers 404 rather than 403 so a private playlist does not
    # confirm it exists; the message here keeps that indistinguishable.
    client = client_returning(404, {"detail": "Not Found"})
    with pytest.raises(PlaylistError, match=MISSING):
        await client.detail(99, 4)


async def test_a_server_error_becomes_a_readable_refusal() -> None:
    client = client_returning(500, {"detail": "boom"})
    with pytest.raises(PlaylistError):
        await client.for_user(99)


async def test_an_unreachable_api_does_not_raise_a_transport_error() -> None:
    def explode(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    client = PlaylistClient(
        "http://api.invalid", "shhh", transport=httpx.MockTransport(explode)
    )

    with pytest.raises(PlaylistError):
        await client.for_user(99)


def test_saved_rows_become_tracks_without_a_search() -> None:
    tracks = to_tracks(PlaylistDetail.model_validate(PLAYLIST), requester_id=7)

    assert len(tracks) == 1
    assert tracks[0].title == "Zanaris Nocturne"
    assert tracks[0].requester_id == 7
    # No Lavalink payload: the audio is looked up when it plays, not now.
    assert not tracks[0].is_playable


def test_saved_rows_keep_the_order_they_were_saved_in() -> None:
    detail = PlaylistDetail.model_validate(
        {
            **PLAYLIST,
            "tracks": [
                {**ROW, "title": "Third", "position": 2},
                {**ROW, "title": "First", "position": 0},
                {**ROW, "title": "Second", "position": 1},
            ],
        }
    )
    assert [t.title for t in to_tracks(detail, requester_id=7)] == [
        "First",
        "Second",
        "Third",
    ]


def test_a_saved_track_keeps_the_cover_it_was_saved_with() -> None:
    # Playback resolution finds a mirror on another source, whose own cover is
    # not the one the user saved, so the saved one is the only right answer.
    tracks = to_tracks(PlaylistDetail.model_validate(PLAYLIST), requester_id=7)

    assert tracks[0].artwork == "https://i.scdn.co/image/abc123"


def test_a_saved_track_keeps_its_isrc_so_a_dead_id_can_recover() -> None:
    tracks = to_tracks(PlaylistDetail.model_validate(PLAYLIST), requester_id=7)
    assert tracks[0].isrc == "USABC1234567"


def test_playlists_are_disabled_when_either_half_of_the_config_is_missing() -> None:
    # A missing config means no control at all, rather than a button that
    # errors when it is pressed.
    assert build_playlist_client("", "key") is None
    assert build_playlist_client("http://api.invalid", "") is None
    assert build_playlist_client("http://api.invalid", "key") is not None


def test_the_picker_offers_the_playlists_it_was_given() -> None:
    picker = PlaylistPicker(_context(), _summaries(4))
    assert len(_select_of(picker)["options"]) == 4


def test_the_picker_caps_at_the_discord_select_limit() -> None:
    picker = PlaylistPicker(_context(), _summaries(40))
    assert len(_select_of(picker)["options"]) == PLAYLISTS_SHOWN
    assert PLAYLISTS_SHOWN <= 25


def test_each_option_says_how_big_it_is_and_whose_it_is() -> None:
    mine = PlaylistSummary(
        id=1, owner_discord_id=1, name="Mine", is_public=False, track_count=12
    )
    shared = mine.model_copy(update={"is_public": True, "track_count": 1})

    assert playlist_option(mine) == "12 tracks · yours"
    assert playlist_option(shared) == "1 track · shared"


def test_the_picker_stays_inside_the_component_budget() -> None:
    picker = PlaylistPicker(_context(), _summaries(PLAYLISTS_SHOWN))
    assert picker._total_children <= 40
    assert picker.content_length() <= 4000


def test_the_confirmation_names_a_few_tracks_and_counts_the_rest() -> None:
    detail = PlaylistDetail.model_validate(
        {
            **PLAYLIST,
            "tracks": [{**ROW, "title": f"Track {i}", "position": i} for i in range(9)],
        }
    )
    message = playlist_queued("Slayer Tunes", to_tracks(detail, requester_id=7))

    assert "Queued **9** tracks" in message
    assert "Track 0" in message
    assert "and 6 more" in message


async def _allow_everyone(user_id: int) -> bool:
    return True


def _context() -> PanelContext:
    return PanelContext(session=cast(Any, None), guard=_allow_everyone)


def _summaries(count: int) -> list[PlaylistSummary]:
    return [
        PlaylistSummary(
            id=index,
            owner_discord_id=99,
            name=f"Playlist {index}",
            is_public=index % 2 == 0,
            track_count=index,
        )
        for index in range(count)
    ]


def _select_of(picker: PlaylistPicker) -> dict[str, Any]:
    return next(
        component
        for row in picker.to_components()[0]["components"]
        if row["type"] == 1
        for component in row["components"]
        if component["type"] == 3
    )
