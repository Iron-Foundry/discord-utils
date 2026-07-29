"""Who is in the voice channel, which is also who may control it.

Control authority is "anyone connected to the channel", and it has to mean the
same thing on Discord and on the web. Discord can read the voice states
directly; the web cannot, so the membership is mirrored into a Valkey set and
both surfaces answer the question from that one place.
"""

from __future__ import annotations

from collections.abc import Iterable

import discord
from valkey.asyncio import Valkey

from music import keys
from music.valkey_io import resolve


def human_ids(channel: discord.VoiceChannel) -> list[int]:
    """Connected members that are not bots."""
    return [member.id for member in channel.members if not member.bot]


def is_deserted(channel: discord.VoiceChannel) -> bool:
    """True when only bots are left, which is when a session should end."""
    return not human_ids(channel)


class VoiceRoster:
    """The live listener set for one voice channel."""

    def __init__(self, valkey: Valkey, voice_channel_id: int) -> None:
        self._valkey = valkey
        self._key = keys.VOICE.format(voice_channel_id=voice_channel_id)

    async def sync(self, user_ids: Iterable[int]) -> None:
        """Replace the roster with the current truth from the gateway."""
        ids = list(user_ids)
        async with self._valkey.pipeline(transaction=True) as pipe:
            pipe.delete(self._key)
            if ids:
                pipe.sadd(self._key, *ids)
                pipe.expire(self._key, keys.SESSION_TTL_SECONDS)
            await pipe.execute()

    async def may_control(self, user_id: int) -> bool:
        """Whether this user is in the channel, and so allowed to control it."""
        return bool(await resolve(self._valkey.sismember(self._key, str(user_id))))

    async def size(self) -> int:
        return int(await resolve(self._valkey.scard(self._key)))
