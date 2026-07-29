"""Search prefixes and the playback provider chain."""

from __future__ import annotations

from music.models import Track
from music.resolve import (
    DEFAULT_SOURCE,
    MIRRORED_SOURCES,
    SOURCE_PREFIXES,
    _playback_queries,
)
from tests.factories import make_track


def test_every_source_maps_to_its_lavalink_prefix() -> None:
    assert SOURCE_PREFIXES == {
        "spotify": "spsearch",
        "youtube": "ytsearch",
        "soundcloud": "scsearch",
    }
    assert DEFAULT_SOURCE in SOURCE_PREFIXES


def test_only_spotify_needs_mirroring() -> None:
    # Spotify holds metadata only; the others stream directly.
    assert set(MIRRORED_SOURCES) == {"spotify"}


def test_mirror_chain_tries_the_isrc_first() -> None:
    queries = _playback_queries(make_track())
    assert queries[0] == ('"USABC1234567"', "ytsearch")
    assert queries[1] == ("Zanaris Nocturne Barbarian Assault", "ytsearch")
    assert queries[2] == ("Zanaris Nocturne Barbarian Assault", "scsearch")


def test_mirror_chain_falls_back_to_text_without_an_isrc() -> None:
    queries = _playback_queries(make_track(isrc=None))
    assert len(queries) == 2
    assert all('"' not in query for query, _ in queries)


def test_a_hyphenated_isrc_is_flattened_before_it_is_searched() -> None:
    # LavaSrc strips the hyphens before running the same query
    # (DefaultMirroringAudioTrackResolver.java:41), and a hyphenated ISRC
    # matches nothing on YouTube.
    queries = _playback_queries(make_track(isrc="US-ABC-12-34567"))
    assert queries[0] == ('"USABC1234567"', "ytsearch")


def test_a_saved_track_is_tried_at_its_own_url_first() -> None:
    # A saved playlist row carries no Lavalink payload, so the URL is the only
    # handle that resolves to exactly the track that was saved.
    queries = _playback_queries(_saved(source="youtube"))
    assert queries[0] == ("https://example.invalid/saved", "ytsearch")


def test_a_saved_track_still_falls_back_when_its_id_is_dead() -> None:
    # The point of storing the ISRC: a dead YouTube id re-resolves instead of
    # the track vanishing from the playlist.
    queries = _playback_queries(_saved(source="youtube"))
    assert queries[1] == ('"USABC1234567"', "ytsearch")
    assert queries[-1][1] == "scsearch"


def test_a_saved_spotify_track_skips_its_url() -> None:
    # A Spotify URL resolves to Spotify, which holds no audio to play.
    queries = _playback_queries(_saved(source="spotify"))
    assert queries[0] == ('"USABC1234567"', "ytsearch")


def test_a_searched_track_never_gets_the_url_step() -> None:
    # It already carries its own audio; only a mirror lookup can apply.
    assert _playback_queries(make_track(source="spotify"))[0][1] == "ytsearch"


def _saved(*, source: str) -> Track:
    return Track(
        identifier="saved",
        title="Zanaris Nocturne",
        author="Barbarian Assault",
        length_ms=180_000,
        is_stream=False,
        uri="https://example.invalid/saved",
        isrc="USABC1234567",
        source=source,
        requested_source=source,
        requester_id=7,
    )
