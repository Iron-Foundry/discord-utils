"""What has already played in one session.

A capped Valkey list, newest first, written the moment a track leaves the deck.
Deliberately not the activity feed: activity records who pressed what, history
records what was heard, and the re-queue controls need the track itself back
rather than a rendered line.

The anonymous per-guild counter is emitted from here too. Both records exist
for the same reason at the same moment, and a track counted but not listed - or
listed but not counted - would make the panel and the stats page disagree about
what played. Only the list is ephemeral; the counter outlives the session.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel
from valkey.asyncio import Valkey

from music import keys
from music.models import Track
from music.stats import TRACK_PLAYED, TRACK_SKIPPED, StatsStream
from music.valkey_io import resolve

# Deep enough to cover a whole evening, small enough that five sessions of it
# stay a rounding error in Valkey - entries carry metadata only.
HISTORY_LIMIT = 100

PLAYED = "played"
SKIPPED = "skipped"

_COUNTER_EVENTS = {PLAYED: TRACK_PLAYED, SKIPPED: TRACK_SKIPPED}


class PlayedTrack(BaseModel):
    """One track that has already finished, and how it ended."""

    at: datetime
    event: str
    track: Track


class PlayHistory:
    """What has played in one voice channel, newest first."""

    def __init__(
        self, valkey: Valkey, voice_channel_id: int, stats: StatsStream
    ) -> None:
        self._valkey = valkey
        self._stats = stats
        self._key = keys.HISTORY.format(voice_channel_id=voice_channel_id)

    async def record(self, track: Track, event: str, listened_ms: int) -> None:
        """Note a finished track, in this session's list and in the counters."""
        await self._stats.track_event(
            _COUNTER_EVENTS[event], track, listened_ms=listened_ms
        )
        await self._push(track, event)

    async def recent(self, count: int = HISTORY_LIMIT) -> list[PlayedTrack]:
        """The newest entries first."""
        raw = await resolve(self._valkey.lrange(self._key, 0, count - 1))
        return [PlayedTrack.model_validate_json(item) for item in raw]

    async def _push(self, track: Track, event: str) -> None:
        entry = PlayedTrack(
            at=datetime.now(UTC), event=event, track=_metadata_only(track)
        )
        async with self._valkey.pipeline(transaction=True) as pipe:
            pipe.lpush(self._key, entry.model_dump_json())
            pipe.ltrim(self._key, 0, HISTORY_LIMIT - 1)
            pipe.expire(self._key, keys.SESSION_TTL_SECONDS)
            await pipe.execute()


def _metadata_only(track: Track) -> Track:
    """The track without its Lavalink audio.

    The payload is by far the largest thing a stored track carries, and a
    re-queued track has its audio looked up at play time regardless - the same
    path a saved playlist row takes. Keeping it would make the history key
    bigger than the session it belongs to.
    """
    return track.model_copy(update={"encoded": "", "payload": {}})
