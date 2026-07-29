"""The per-session activity feed.

A capped Valkey list, newest first, so the panel can render "who did what" for
a session without any of it outliving the session. Nothing here is ever
persisted to Postgres.

Entries carry the actor's name as well as their id. The panel can render a
`<@id>` mention and let Discord resolve it, but the website has no way to turn
a snowflake into a person, so the name is attached here where the guild is in
reach.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel
from valkey.asyncio import Valkey

from music import keys
from music.naming import NameLookup
from music.valkey_io import resolve

ACTIVITY_LIMIT = 25


class ActivityEntry(BaseModel):
    """One interaction with a session."""

    at: datetime
    actor_id: int
    actor_name: str = ""
    action: str
    detail: str = ""

    def render(self) -> str:
        """A single line for the panel's activity view."""
        stamp = int(self.at.timestamp())
        suffix = f" - {self.detail}" if self.detail else ""
        return f"<t:{stamp}:R> <@{self.actor_id}> {self.action}{suffix}"


class ActivityFeed:
    """The recent interactions for one voice channel."""

    def __init__(
        self,
        valkey: Valkey,
        voice_channel_id: int,
        names: NameLookup | None = None,
    ) -> None:
        self._valkey = valkey
        self._key = keys.ACTIVITY.format(voice_channel_id=voice_channel_id)
        self._names = names

    async def push(self, actor_id: int, action: str, detail: str = "") -> None:
        """Record an interaction, dropping the oldest once the cap is reached."""
        entry = ActivityEntry(
            at=datetime.now(UTC),
            actor_id=actor_id,
            actor_name=(self._names(actor_id) or "") if self._names else "",
            action=action,
            detail=detail,
        )
        async with self._valkey.pipeline(transaction=True) as pipe:
            pipe.lpush(self._key, entry.model_dump_json())
            pipe.ltrim(self._key, 0, ACTIVITY_LIMIT - 1)
            pipe.expire(self._key, keys.SESSION_TTL_SECONDS)
            await pipe.execute()

    async def recent(self, count: int = ACTIVITY_LIMIT) -> list[ActivityEntry]:
        """The newest entries first."""
        raw = await resolve(self._valkey.lrange(self._key, 0, count - 1))
        return [ActivityEntry.model_validate_json(item) for item in raw]
