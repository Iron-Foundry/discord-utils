"""Counter events for api-backend to consume.

A Valkey stream rather than pubsub: playback must never block on a database
write, and an api-backend restart must not lose the events that happened while
it was down. A consumer group picks up where it left off; pubsub would simply
have dropped them.

No user id is written here. Counters are per guild and per track, which is the
design's one-way privacy decision - per-user history cannot be reconstructed
later, including retroactively.
"""

from __future__ import annotations

from loguru import logger
from valkey.asyncio import Valkey

from music import keys
from music.models import Track

STREAM_MAX_LENGTH = 10_000

TRACK_PLAYED = "track_played"
TRACK_SKIPPED = "track_skipped"
SESSION_STARTED = "session_started"
SESSION_ENDED = "session_ended"


class StatsStream:
    """Appends music counter events for api-backend."""

    def __init__(self, valkey: Valkey, guild_id: int) -> None:
        self._valkey = valkey
        self._guild_id = guild_id

    async def track_event(
        self, event: str, track: Track, *, listened_ms: int = 0
    ) -> None:
        """Record a play or a skip, keyed for ISRC-first identity."""
        await self._emit(
            {
                "event": event,
                "guild_id": str(self._guild_id),
                "isrc": track.isrc or "",
                "title": track.title,
                "author": track.author,
                "identifier": track.identifier,
                "requested_source": track.requested_source,
                "played_source": track.played_source or track.source,
                "length_ms": str(track.length_ms),
                "listened_ms": str(listened_ms),
            }
        )

    async def session_event(self, event: str, voice_channel_id: int) -> None:
        await self._emit(
            {
                "event": event,
                "guild_id": str(self._guild_id),
                "voice_channel_id": str(voice_channel_id),
            }
        )

    async def _emit(self, fields: dict[str, str]) -> None:
        try:
            await self._valkey.xadd(
                keys.EVENTS, fields, maxlen=STREAM_MAX_LENGTH, approximate=True
            )
        except Exception as exc:
            # Stats are not worth failing playback over.
            logger.warning("Music: could not emit {} event: {}", fields["event"], exc)
