"""Value objects shared by the music module."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, cast

import wavelink
from pydantic import BaseModel, Field
from wavelink.types.tracks import TrackPayload


class LoopMode(StrEnum):
    """How the queue behaves when a track ends."""

    OFF = "off"
    TRACK = "track"
    QUEUE = "queue"


class Track(BaseModel):
    """One queued track, serialisable into Valkey.

    ``requested_source`` is where the user asked from and ``played_source`` is
    where the audio actually came from. They differ whenever Spotify is
    involved, because Spotify cannot be streamed and the audio is mirrored from
    another source, so keeping one field would silently split play counts.

    The whole Lavalink payload is kept so the track can be handed back to
    Lavalink after a round trip through Valkey without re-searching for it. A
    track loaded from a saved playlist has no payload, because api-backend
    stores metadata rather than audio; such a track is queued as it is and its
    audio is looked up at play time.
    """

    encoded: str = ""
    identifier: str
    title: str
    author: str
    length_ms: int
    is_stream: bool
    uri: str | None = None
    artwork: str | None = None
    isrc: str | None = None
    source: str
    requested_source: str
    played_source: str | None = None
    requester_id: int
    # Stamped when the track is queued, from the guild member behind the id.
    # The website cannot resolve a snowflake by itself, so a track that reaches
    # it unnamed is shown as a bare id.
    requester_name: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_playable(self) -> bool:
        """Whether Lavalink audio is attached, or only metadata."""
        return bool(self.payload)

    @classmethod
    def from_playable(
        cls,
        playable: wavelink.Playable,
        *,
        requested_source: str,
        requester_id: int,
    ) -> Track:
        """Capture a Lavalink search result as a storable track."""
        return cls(
            encoded=playable.encoded,
            identifier=playable.identifier,
            title=playable.title,
            author=playable.author,
            length_ms=playable.length,
            is_stream=playable.is_stream,
            uri=playable.uri,
            artwork=playable.artwork,
            isrc=playable.isrc,
            source=playable.source,
            requested_source=requested_source,
            requester_id=requester_id,
            payload=dict(playable.raw_data),
        )

    def to_playable(self) -> wavelink.Playable:
        """Rebuild the wavelink track from the stored Lavalink payload.

        Constructing ``Playable`` directly is only discouraged for hand-built
        data. This payload came from Lavalink unchanged, which is the case the
        constructor exists for, and it avoids a second search per queued track.
        """
        return wavelink.Playable(cast(TrackPayload, self.payload))


class LeasedBot(BaseModel):
    """A player bot currently bound to one voice channel."""

    bot_index: int
    nickname: str
    voice_channel_id: int


class PoolSlot(BaseModel):
    """The observed state of one slot in the pool."""

    bot_index: int
    voice_channel_id: int | None = None

    @property
    def is_free(self) -> bool:
        return self.voice_channel_id is None


class PoolExhaustedError(RuntimeError):
    """Every player bot is already leased.

    Carries the occupied slots so the caller can tell the user which channels
    are holding the bots rather than just refusing.
    """

    def __init__(self, slots: list[PoolSlot]) -> None:
        self.slots = slots
        channels = ", ".join(
            f"<#{slot.voice_channel_id}>" for slot in slots if slot.voice_channel_id
        )
        super().__init__(f"All music bots are busy in: {channels}")
