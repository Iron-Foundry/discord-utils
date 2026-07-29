"""One voice channel's playback session.

Playback is driven from the Valkey queue, not from wavelink's in-memory one.
wavelink's own queue is left untouched and its autoplay stays disabled, so the
only thing that decides what plays next is `advance`. That keeps the queue the
web surface reads and the queue Discord plays from as the same object.
"""

from __future__ import annotations

import wavelink
from loguru import logger
from valkey.asyncio import Valkey

from music.activity import ActivityFeed
from music.history import PLAYED, SKIPPED, PlayHistory
from music.models import LoopMode, Track
from music.naming import NameLookup, stamp_requesters
from music.queue import TrackQueue
from music.resolve import (
    DEFAULT_SOURCE,
    SearchResult,
    resolve_playback,
    search_tracks,
)
from music.state import SessionState
from music.stats import StatsStream
from music.transport import Transport

# Lavalink reports why a track ended. "replaced" and "stopped" are our own
# doing - skip and stop already decided what happens next - so only the reasons
# that mean the track ran out advance the queue.
ADVANCING_REASONS = frozenset({"finished", "loadFailed"})


class MusicSession(Transport):
    """Queue, transport and state for one voice channel."""

    def __init__(
        self,
        valkey: Valkey,
        player: wavelink.Player,
        voice_channel_id: int,
        guild_id: int,
        names: NameLookup | None = None,
    ) -> None:
        self.voice_channel_id = voice_channel_id
        self._names = names
        self.player = player
        self.queue = TrackQueue(valkey, voice_channel_id)
        self.state = SessionState(valkey, voice_channel_id)
        self.activity = ActivityFeed(valkey, voice_channel_id, names)
        self.stats = StatsStream(valkey, guild_id)
        self.history = PlayHistory(valkey, voice_channel_id, self.stats)

    @property
    def node(self) -> wavelink.Node:
        return self.player.node

    async def search(
        self, query: str, *, requester_id: int, source: str | None = None
    ) -> SearchResult:
        """Resolve a query without queueing anything.

        Separate from `enqueue` because a plain search returns alternatives the
        user is entitled to choose between, and queueing all of them - which is
        what a single combined step did - is never what anyone meant.
        """
        return await search_tracks(
            query,
            node=self.node,
            requester_id=requester_id,
            source=source or DEFAULT_SOURCE,
        )

    async def enqueue(self, tracks: list[Track], *, actor_id: int, label: str) -> None:
        """Queue tracks the caller has settled on, and start playing if idle."""
        stamp_requesters(tracks, self._names)
        await self.queue.add(tracks)
        await self.activity.push(actor_id, "queued", label)
        if self.player.playing:
            # Already playing, so only the up-next block changed.
            await self.changed()
        else:
            await self.play_next()

    async def play_next(self) -> Track | None:
        """Take the next track and play it. Returns None when the queue is dry."""
        if await self.state.shuffle():
            track = await self.queue.pop_random()
        else:
            track = await self.queue.pop()
        if track is None:
            await self.state.set_current(None)
            await self.changed()
            return None
        return await self._play(track)

    async def advance(self, reason: str) -> Track | None:
        """React to a track ending, honouring the loop mode."""
        if reason not in ADVANCING_REASONS:
            return None

        current = await self.state.current()
        if current is not None:
            await self.history.record(current, PLAYED, current.length_ms)

        mode = await self.state.loop()
        if mode is LoopMode.TRACK and current is not None:
            return await self._play(current)
        if mode is LoopMode.QUEUE and current is not None:
            await self.queue.add([current])
        return await self.play_next()

    async def skip(self, actor_id: int) -> Track | None:
        """Drop the current track and play the next one."""
        current = await self.state.current()
        if current is not None:
            await self.history.record(current, SKIPPED, self.player.position)
        await self.activity.push(actor_id, "skipped", current.title if current else "")
        nxt = await self.play_next()
        if nxt is None:
            await self.player.stop(force=True)
        return nxt

    async def jump(self, actor_id: int, index: int) -> Track | None:
        """Skip straight to a queued track, dropping everything before it."""
        tracks = await self.queue.all()
        if not 0 <= index < len(tracks):
            return None
        target = tracks[index]
        await self.queue.replace(tracks[index + 1 :])
        await self.activity.push(actor_id, "jumped to", target.title)
        return await self._play(target)

    async def _play(self, track: Track) -> Track:
        playable, played_source = await resolve_playback(track, node=self.node)
        track.played_source = played_source
        # A track saved without cover art can only recover one from the audio
        # that was just resolved for it, so this is the moment to take it.
        track.artwork = track.artwork or playable.artwork
        await self.player.play(playable, volume=await self.state.volume())
        await self.state.set_current(track)
        logger.info(
            "Music: playing {!r} from {} in channel {}",
            track.title,
            played_source,
            self.voice_channel_id,
        )
        await self.changed()
        return track
