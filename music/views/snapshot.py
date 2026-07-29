"""A frozen read of a session, taken once per render.

The panel is built from a snapshot rather than from the live session so that a
render never issues a second round of Valkey reads halfway through, and so the
view can be built and asserted in a test without a player attached.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from music.models import LoopMode, Track
from music.session import MusicSession

UPCOMING_SHOWN = 3
# Discord caps a select at 25 options, so the jump control can only ever offer
# the head of the queue. One LRANGE covers both it and the up-next block.
JUMP_OPTIONS = 25


@dataclass(slots=True)
class PanelSnapshot:
    """Everything the panel needs, read once."""

    voice_channel_id: int
    current: Track | None = None
    queue_head: list[Track] = field(default_factory=list)
    queue_length: int = 0
    remaining_ms: int = 0
    volume: int = 100
    loop: LoopMode = LoopMode.OFF
    shuffle: bool = False
    paused: bool = False
    ends_at: datetime | None = None

    @property
    def is_idle(self) -> bool:
        return self.current is None

    @property
    def upcoming(self) -> list[Track]:
        """The few tracks the panel actually names."""
        return self.queue_head[:UPCOMING_SHOWN]


async def take_snapshot(session: MusicSession) -> PanelSnapshot:
    """Read the whole session state in one pass."""
    current = await session.state.current()
    return PanelSnapshot(
        voice_channel_id=session.voice_channel_id,
        current=current,
        queue_head=await session.queue.peek(JUMP_OPTIONS),
        queue_length=await session.queue.length(),
        remaining_ms=await session.queue.remaining_ms(),
        volume=await session.state.volume(),
        loop=await session.state.loop(),
        shuffle=await session.state.shuffle(),
        paused=session.player.paused,
        ends_at=_ends_at(current, session.player.position),
    )


def _ends_at(current: Track | None, position_ms: int) -> datetime | None:
    """When the current track runs out, as an absolute instant.

    Absolute rather than a countdown on purpose: rendered as a Discord relative
    timestamp, the viewer's own client counts it down, so the panel never needs
    a timer and never spends channel edit budget just to tick.
    """
    if current is None or current.is_stream:
        return None
    left = max(0, current.length_ms - position_ms)
    return datetime.now(UTC) + timedelta(milliseconds=left)
