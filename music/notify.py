"""Telling the web that a session moved.

The notice carries no state on purpose: it names the channel and nothing else,
and api-backend reads the session out of Valkey itself. That keeps exactly one
place shaping the web payload, so a field added for the website never has to be
added here too.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Awaitable, Callable, Sequence

from loguru import logger
from valkey.asyncio import Valkey

from music import keys
from music.session import MusicSession

CHANGED = "changed"
CLOSED = "closed"

# Slow enough to cost nothing, frequent enough that a watcher can call a session
# dead after a couple of missed rounds and still be well inside its Valkey TTL.
KEEPALIVE_SECONDS = 60


async def publish_state(valkey: Valkey, session: MusicSession) -> None:
    """Record what only the player knows, then say the session moved."""
    await session.state.set_live(
        paused=session.player.paused, position_ms=session.player.position
    )
    await notify(valkey, session.voice_channel_id, CHANGED)


async def publish_closed(valkey: Valkey, voice_channel_id: int) -> None:
    """Say a session ended, so a web viewer stops showing a dead player."""
    await notify(valkey, voice_channel_id, CLOSED)


def with_state_publish(
    session: MusicSession, valkey: Valkey, downstream: Callable[[], Awaitable[None]]
) -> Callable[[], Awaitable[None]]:
    """Chain the state notice onto whatever already redraws the panel."""

    async def changed() -> None:
        await downstream()
        await publish_state(valkey, session)

    return changed


class StateKeepalive:
    """Re-announce every live session on a slow tick.

    A session that ends cleanly publishes a closed notice, but a killed process
    publishes nothing at all - its keys simply expire. Without a heartbeat the
    website has no way to tell a quiet session from a dead one, and would keep
    showing a player for a bot that left. Hearing nothing for a few ticks is
    what lets a watcher drop it.

    It also refreshes the stored position, so a browser extrapolating between
    state changes cannot drift far on a long track.
    """

    def __init__(
        self, valkey: Valkey, sessions: Callable[[], Sequence[MusicSession]]
    ) -> None:
        self._valkey = valkey
        self._sessions = sessions
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="music-keepalive")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def round(self) -> None:
        """Announce every session live right now."""
        for session in self._sessions():
            await publish_state(self._valkey, session)

    async def _run(self) -> None:
        # Self-rescheduling rather than a fixed tick: the next sleep only starts
        # once this round has finished, so a slow Valkey cannot stack rounds up
        # behind each other.
        while True:
            try:
                await asyncio.sleep(KEEPALIVE_SECONDS)
                await self.round()
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning("Music: keepalive round failed: {}", exc)


async def notify(valkey: Valkey, voice_channel_id: int, event: str) -> None:
    payload = json.dumps({"voice_channel_id": voice_channel_id, "event": event})
    try:
        await valkey.publish(keys.STATE, payload)
    except Exception as exc:
        # A web viewer going stale must never take Discord playback with it.
        logger.warning("Music: could not publish state for {}: {}", event, exc)
