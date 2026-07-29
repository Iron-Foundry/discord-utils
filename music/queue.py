"""The upcoming-track queue for one voice channel, held in Valkey.

A Valkey list, so the common operations - append and take the next - are single
round trips at either end. Reorderings (remove, move) rewrite the whole
list inside a transaction instead, because a list has no index-delete: the usual
LSET-sentinel plus LREM trick would also delete a genuine duplicate of that
sentinel. Queues are short enough that a rewrite is cheaper than being clever.

The queue lives and dies with the session, so it carries the same TTL as the
lease and is refreshed alongside it.
"""

from __future__ import annotations

import secrets
from typing import Any

from valkey.asyncio import Valkey

from music import keys
from music.models import Track
from music.valkey_io import resolve

QUEUE_KEY = keys.QUEUE
QUEUE_TTL_SECONDS = keys.SESSION_TTL_SECONDS
MAX_QUEUE_LENGTH = 500


class QueueFullError(RuntimeError):
    """The queue is at its cap and cannot take more tracks."""


class TrackQueue:
    """The pending tracks for one voice channel."""

    def __init__(self, valkey: Valkey, voice_channel_id: int) -> None:
        self._valkey = valkey
        self._key = QUEUE_KEY.format(voice_channel_id=voice_channel_id)

    async def add(self, tracks: list[Track]) -> int:
        """Append tracks and return how many the queue now holds."""
        if not tracks:
            return await self.length()

        length = await self.length()
        if length + len(tracks) > MAX_QUEUE_LENGTH:
            raise QueueFullError(
                f"Queue holds {length} of {MAX_QUEUE_LENGTH} tracks,"
                f" cannot add {len(tracks)} more"
            )

        await resolve(
            self._valkey.rpush(self._key, *(t.model_dump_json() for t in tracks))
        )
        await self.touch()
        return length + len(tracks)

    async def add_next(self, track: Track) -> None:
        """Put a track at the front of the queue."""
        await resolve(self._valkey.lpush(self._key, track.model_dump_json()))
        await self.touch()

    async def pop(self) -> Track | None:
        """Take the next track off the front."""
        raw = await resolve(self._valkey.lpop(self._key))
        return _decode(raw)

    async def peek(self, count: int) -> list[Track]:
        """The next ``count`` tracks, without removing them."""
        return _decode_all(await resolve(self._valkey.lrange(self._key, 0, count - 1)))

    async def all(self) -> list[Track]:
        """Every queued track in order."""
        return _decode_all(await resolve(self._valkey.lrange(self._key, 0, -1)))

    async def length(self) -> int:
        return await resolve(self._valkey.llen(self._key))

    async def remaining_ms(self) -> int:
        """Total duration of everything still queued."""
        return sum(track.length_ms for track in await self.all())

    async def remove(self, index: int) -> Track | None:
        """Drop the track at ``index``, returning it."""
        tracks = await self.all()
        if not 0 <= index < len(tracks):
            return None
        removed = tracks.pop(index)
        await self.replace(tracks)
        return removed

    async def move(self, source: int, destination: int) -> Track | None:
        """Move the track at ``source`` to ``destination``."""
        tracks = await self.all()
        if not 0 <= source < len(tracks) or not 0 <= destination < len(tracks):
            return None
        track = tracks.pop(source)
        tracks.insert(destination, track)
        await self.replace(tracks)
        return track

    async def pop_random(self) -> Track | None:
        """Take a track at random, which is what shuffle mode plays next.

        Drawn at play time rather than by reordering the queue up front, so the
        queue a listener reads still shows the order tracks were added in and
        turning shuffle off resumes that order.
        """
        length = await self.length()
        if length == 0:
            return None
        return await self.remove(secrets.SystemRandom().randrange(length))

    async def clear(self) -> None:
        await self._valkey.delete(self._key)

    async def touch(self) -> None:
        """Refresh the TTL so the queue outlives nothing but its session."""
        await self._valkey.expire(self._key, QUEUE_TTL_SECONDS)

    async def replace(self, tracks: list[Track]) -> None:
        """Swap the whole queue for a new ordering."""
        # One transaction, so a reader never sees a half-rebuilt queue.
        async with self._valkey.pipeline(transaction=True) as pipe:
            pipe.delete(self._key)
            if tracks:
                pipe.rpush(self._key, *(t.model_dump_json() for t in tracks))
                pipe.expire(self._key, QUEUE_TTL_SECONDS)
            await pipe.execute()


def _decode(raw: Any) -> Track | None:
    if raw is None:
        return None
    return Track.model_validate_json(raw)


def _decode_all(raw: list[Any]) -> list[Track]:
    return [track for track in map(_decode, raw) if track is not None]
