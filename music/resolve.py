"""Turns a user's query into tracks, and a track into playable audio.

Two distinct steps, deliberately separated:

Search runs when the user queues something. A bare query defaults to Spotify
because Spotify results carry an ISRC, which is the only stable identity a song
has across sources - the same song queued from Spotify by one person and from
YouTube by another otherwise counts as two different songs.

Playback resolution runs at play time, for every track that holds metadata
rather than audio. Spotify is one such case: its audio cannot be streamed by a
bot, and LavaSrc normally mirrors it server-side inside its own `process()`
call and reports nothing back, so the client can never tell what actually
played. Doing the same lookup here instead, with LavaSrc's own ISRC-first
provider order, makes `played_source` a real observable value. A track loaded
from a saved playlist is the other case, and it takes the same path. Either way
it costs one extra search per track actually played, not per track queued.
"""

from __future__ import annotations

from dataclasses import dataclass

import wavelink
from loguru import logger

from music.models import Track

SOURCE_PREFIXES = {
    "spotify": "spsearch",
    "youtube": "ytsearch",
    "soundcloud": "scsearch",
}
DEFAULT_SOURCE = "spotify"
FALLBACK_SOURCE = "youtube"
FALLBACK_PREFIX = SOURCE_PREFIXES[FALLBACK_SOURCE]

# Sources that hold metadata only and must be mirrored before they can play.
MIRRORED_SOURCES = frozenset({"spotify"})


class NoResultsError(RuntimeError):
    """Nothing matched the query."""


@dataclass(slots=True)
class SearchResult:
    """What a query resolved to, and whether the user still has a choice to make.

    Lavalink answers a link with exactly one track and a search with many, but
    wavelink returns `list[Playable]` for both and drops the load type
    (`node.py:960-974`). A list longer than one is therefore precisely a search
    with alternatives, not a guess.
    """

    tracks: list[Track]
    playlist: str | None = None

    @property
    def needs_choice(self) -> bool:
        """True when the user searched and got alternatives worth picking from."""
        return self.playlist is None and len(self.tracks) > 1

    @property
    def label(self) -> str:
        """What to call this result in a confirmation."""
        return self.playlist or self.tracks[0].title


async def search_tracks(
    query: str,
    *,
    node: wavelink.Node,
    requester_id: int,
    source: str = DEFAULT_SOURCE,
) -> SearchResult:
    """Resolve a query into tracks, plus the playlist name when it was one.

    The node is always passed explicitly. `Pool` picks a node by player count
    and ignores which bot owns it, so letting it choose would search over
    another bot's node.
    """
    prefix = SOURCE_PREFIXES.get(source, SOURCE_PREFIXES[DEFAULT_SOURCE])
    found = await wavelink.Playable.search(query, source=prefix, node=node)

    if not found and source == DEFAULT_SOURCE and "://" not in query:
        logger.debug("Music: no {} result for {!r}, retrying on YouTube", source, query)
        found = await wavelink.Playable.search(
            query, source=SOURCE_PREFIXES[FALLBACK_SOURCE], node=node
        )

    if not found:
        raise NoResultsError(f"Nothing found for {query!r}")

    return SearchResult(
        tracks=[
            Track.from_playable(
                playable, requested_source=playable.source, requester_id=requester_id
            )
            for playable in found
        ],
        playlist=found.name if isinstance(found, wavelink.Playlist) else None,
    )


async def resolve_playback(
    track: Track, *, node: wavelink.Node
) -> tuple[wavelink.Playable, str]:
    """Return the audio to play for a track, and the source it came from."""
    if track.is_playable and track.source not in MIRRORED_SOURCES:
        return track.to_playable(), track.source

    for query, source in _playback_queries(track):
        found = await wavelink.Playable.search(query, source=source, node=node)
        playables = list(found)
        if playables:
            return playables[0], playables[0].source

    raise NoResultsError(f"No playable audio found for {track.title!r}")


def _playback_queries(track: Track) -> list[tuple[str, str]]:
    """Where to look for a track's audio, in order.

    A track restored from a saved playlist is tried at its own URL first, which
    resolves to exactly the track that was saved. Everything after that is
    LavaSrc's own provider order - the ISRC quoted, then the text - which is
    also the whole chain for a Spotify track, since Spotify holds no audio to
    link to.
    """
    text = f"{track.title} {track.author}".strip()
    queries: list[tuple[str, str]] = []

    if not track.is_playable and track.uri and track.source not in MIRRORED_SOURCES:
        # wavelink applies no search prefix at all to a URL (`tracks.py:350`),
        # so the source named here only matters if this turns out not to be one.
        queries.append((track.uri, SOURCE_PREFIXES.get(track.source, FALLBACK_PREFIX)))
    if track.isrc:
        # Hyphens are stripped because LavaSrc strips them before running the
        # same query (`DefaultMirroringAudioTrackResolver.java:41`), and a
        # hyphenated ISRC matches nothing on YouTube.
        queries.append((f'"{_bare_isrc(track.isrc)}"', SOURCE_PREFIXES["youtube"]))
    queries.append((text, SOURCE_PREFIXES["youtube"]))
    queries.append((text, SOURCE_PREFIXES["soundcloud"]))
    return queries


def _bare_isrc(isrc: str) -> str:
    return isrc.replace("-", "")
