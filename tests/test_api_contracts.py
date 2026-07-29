"""Guard: the playlist payload discord-utils reads matches the shared contract.

The monorepo-root fixture pins the shape api-backend emits from
`/music/bot/{discord_user_id}/playlists/{id}`. Drift on either side breaks this.
Skipped when run outside the monorepo checkout (submodule-only CI).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from music.playlists import PlaylistDetail, PlaylistSummary, to_tracks

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"

pytestmark = pytest.mark.skipif(
    not _FIXTURES.exists(),
    reason="root fixtures/ not present (submodule-only checkout)",
)


def fixture() -> dict[str, Any]:
    return json.loads((_FIXTURES / "music_playlist.json").read_text())


def test_the_client_parses_exactly_what_the_api_emits() -> None:
    playlist = PlaylistDetail.model_validate(fixture())

    assert playlist.name == "Slayer Tunes"
    assert playlist.track_count == 2
    assert [track.position for track in playlist.tracks] == [0, 1]


def test_every_field_the_client_needs_is_in_the_contract() -> None:
    body = fixture()
    required = set(PlaylistSummary.model_fields) | {"tracks"}

    assert required <= set(body), (
        "playlist payload keys drifted from fixtures/music_playlist.json"
    )


def test_every_track_field_the_client_needs_is_in_the_contract() -> None:
    row = fixture()["tracks"][0]
    needed = {"source", "identifier", "title", "author", "duration_ms", "position"}

    assert needed <= set(row)


def test_a_contract_playlist_becomes_queueable_tracks() -> None:
    tracks = to_tracks(PlaylistDetail.model_validate(fixture()), requester_id=7)

    assert [track.title for track in tracks] == ["Zanaris Nocturne", "Sea Shanty 2"]
    # The second row has no ISRC, which is what a YouTube save looks like, and
    # it still has to load.
    assert tracks[1].isrc is None
    assert all(not track.is_playable for track in tracks)
