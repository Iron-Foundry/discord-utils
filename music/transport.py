"""Transport controls, and the one place a state change is announced.

Split from `MusicSession` so that every control passes through `changed()`
exactly once. The panel is edited only when something actually changed - never
on a timer - so this is the single hook that keeps the rendered panel honest
without polling Discord.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import wavelink
from loguru import logger

from music.activity import ActivityFeed
from music.models import LoopMode
from music.queue import TrackQueue
from music.state import SessionState

StateListener = Callable[[], Awaitable[None]]


class Transport:
    """Pause, stop, seek, volume, loop and shuffle for one player."""

    player: wavelink.Player
    queue: TrackQueue
    state: SessionState
    activity: ActivityFeed
    on_change: StateListener | None = None

    async def changed(self) -> None:
        """Tell whoever is rendering this session that it moved."""
        if self.on_change is None:
            return
        try:
            await self.on_change()
        except Exception as exc:
            # A panel that failed to redraw must never take playback with it.
            logger.warning("Music: panel refresh failed: {}", exc)

    async def pause(self, actor_id: int, paused: bool) -> None:
        await self.player.pause(paused)
        await self.activity.push(actor_id, "paused" if paused else "resumed")
        await self.changed()

    async def stop(self, actor_id: int) -> None:
        """Clear the queue and stop. The session itself is torn down by the pool."""
        await self.queue.clear()
        await self.state.set_current(None)
        await self.player.stop(force=True)
        await self.activity.push(actor_id, "stopped playback")
        await self.changed()

    async def seek(self, actor_id: int, position_ms: int) -> None:
        current = await self.state.current()
        if current is None or not self.player.current:
            return
        await self.player.seek(max(0, min(current.length_ms, position_ms)))
        await self.activity.push(actor_id, "seeked", f"{position_ms // 1000}s")
        await self.changed()

    async def set_volume(self, actor_id: int, value: int) -> int:
        volume = await self.state.set_volume(value)
        await self.player.set_volume(volume)
        await self.activity.push(actor_id, "set volume", f"{volume}%")
        await self.changed()
        return volume

    async def set_loop(self, actor_id: int, mode: LoopMode) -> None:
        await self.state.set_loop(mode)
        await self.activity.push(actor_id, "set loop", mode.value)
        await self.changed()

    async def set_shuffle(self, actor_id: int, enabled: bool) -> None:
        """Turn random play on or off.

        A mode rather than a one-off reorder: the queue keeps the order tracks
        were added in and `play_next` draws at random while this is on, so
        turning it off resumes that order instead of leaving a scrambled queue
        behind.
        """
        await self.state.set_shuffle(enabled)
        await self.activity.push(actor_id, "shuffle", "on" if enabled else "off")
        await self.changed()

    async def remove(self, actor_id: int, index: int) -> str | None:
        """Drop one queued track, returning its title."""
        track = await self.queue.remove(index)
        if track is None:
            return None
        await self.activity.push(actor_id, "removed", track.title)
        await self.changed()
        return track.title

    async def move(self, actor_id: int, source: int, destination: int) -> str | None:
        """Reorder one queued track, returning its title."""
        track = await self.queue.move(source, destination)
        if track is None:
            return None
        await self.activity.push(
            actor_id, "moved", f"{track.title} to #{destination + 1}"
        )
        await self.changed()
        return track.title
