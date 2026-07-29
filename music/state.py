"""The live state of one voice channel's session.

Kept in the same Valkey hash the pool writes its lease into, so a reader gets
the bot, the nickname, the current track and the transport settings in a single
round trip. api-backend reads this hash directly in a later stage, which is why
it holds display state rather than object references.
"""

from __future__ import annotations

from datetime import UTC, datetime

from valkey.asyncio import Valkey

from music import keys
from music.models import LoopMode, Track
from music.valkey_io import decode_mapping, resolve

DEFAULT_VOLUME = 60
MAX_VOLUME = 150


class SessionState:
    """Reads and writes the session hash for one voice channel."""

    def __init__(self, valkey: Valkey, voice_channel_id: int) -> None:
        self._valkey = valkey
        self._key = keys.SESSION.format(voice_channel_id=voice_channel_id)

    async def read(self) -> dict[str, str]:
        return decode_mapping(await resolve(self._valkey.hgetall(self._key)))

    async def current(self) -> Track | None:
        """The track playing right now, or None when nothing is."""
        raw = await resolve(self._valkey.hget(self._key, "track"))
        if not raw:
            return None
        return Track.model_validate_json(raw)

    async def set_current(self, track: Track | None) -> None:
        if track is None:
            await resolve(self._valkey.hdel(self._key, "track"))
            return
        await self._write(track=track.model_dump_json())

    async def volume(self) -> int:
        raw = await resolve(self._valkey.hget(self._key, "volume"))
        return int(raw) if raw else DEFAULT_VOLUME

    async def set_volume(self, value: int) -> int:
        """Clamp and store the volume, returning what was actually set."""
        clamped = max(0, min(MAX_VOLUME, value))
        await self._write(volume=str(clamped))
        return clamped

    async def set_live(self, *, paused: bool, position_ms: int) -> None:
        """Store what only the player knows, for readers that have no player.

        The panel takes these off `wavelink.Player` directly. api-backend has no
        player and no gateway, so anything it needs that lives in memory has to
        be written down here or it cannot render a progress bar at all.
        `updated_at` is what lets a browser extrapolate the position between
        state changes rather than polling for it.
        """
        await self._write(
            paused="1" if paused else "0",
            position_ms=str(max(0, position_ms)),
            updated_at=str(datetime.now(UTC).timestamp()),
        )

    async def set_channel(self, *, guild_id: int, name: str) -> None:
        """Name the channel, so a web reader need not resolve it over Discord."""
        await self._write(guild_id=str(guild_id), channel_name=name)

    async def initialise(self) -> None:
        """Write the starting modes down rather than leaving them implicit.

        `volume()` and `loop()` fall back to a default when their field is
        absent, so the player behaves correctly without this. api-backend reads
        the hash directly rather than calling them, though, and an unwritten
        default reads there as zero - which showed on the website as a volume
        slider pinned to 0% for every session nobody had touched the volume on.
        """
        await self._write(
            volume=str(DEFAULT_VOLUME), loop=LoopMode.OFF.value, shuffle="0"
        )

    async def shuffle(self) -> bool:
        """Whether the next track is drawn at random rather than taken in order."""
        return await resolve(self._valkey.hget(self._key, "shuffle")) in (b"1", "1")

    async def set_shuffle(self, enabled: bool) -> None:
        await self._write(shuffle="1" if enabled else "0")

    async def loop(self) -> LoopMode:
        raw = await resolve(self._valkey.hget(self._key, "loop"))
        if not raw:
            return LoopMode.OFF
        text = raw.decode() if isinstance(raw, bytes) else str(raw)
        return LoopMode(text)

    async def set_loop(self, mode: LoopMode) -> None:
        await self._write(loop=mode.value)

    async def _write(self, **fields: str) -> None:
        await resolve(self._valkey.hset(self._key, mapping=dict(fields)))
        await self._valkey.expire(self._key, keys.SESSION_TTL_SECONDS)
