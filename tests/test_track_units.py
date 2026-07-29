"""Track capture and the round trip back to Lavalink."""

from __future__ import annotations

from music.models import LoopMode, Track
from tests.factories import make_payload, make_playable, make_track


def test_from_playable_captures_the_identity_fields() -> None:
    track = make_track()
    assert track.title == "Zanaris Nocturne"
    assert track.author == "Barbarian Assault"
    assert track.isrc == "USABC1234567"
    assert track.source == "spotify"
    assert track.length_ms == 180_000


def test_requested_and_played_source_are_separate() -> None:
    track = make_track()
    assert track.requested_source == "spotify"
    # Nothing has played yet, so there is no played source to report.
    assert track.played_source is None
    track.played_source = "youtube"
    assert track.requested_source == "spotify"


def test_round_trip_through_json_survives_valkey() -> None:
    track = make_track()
    restored = Track.model_validate_json(track.model_dump_json())
    assert restored == track


def test_to_playable_rebuilds_the_lavalink_track() -> None:
    original = make_playable()
    track = Track.from_playable(
        original, requested_source=original.source, requester_id=1
    )
    rebuilt = track.to_playable()
    assert rebuilt.encoded == original.encoded
    assert rebuilt.identifier == original.identifier
    assert rebuilt.isrc == original.isrc


def test_track_without_isrc_is_allowed() -> None:
    track = Track.from_playable(
        make_playable(isrc=None, source="youtube"),
        requested_source="youtube",
        requester_id=1,
    )
    assert track.isrc is None
    assert "isrc" not in make_payload(isrc=None)["info"]


def test_loop_modes() -> None:
    assert [mode.value for mode in LoopMode] == ["off", "track", "queue"]
