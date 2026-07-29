"""Leases the player bots to voice channels.

One bot serves at most one voice channel, because a Discord client holds at most
one voice connection per guild. The lease is the Valkey key itself: `SET NX`
either wins the slot or it does not, so two concurrent commands can never be
handed the same bot.

Leases carry a TTL and are refreshed by a heartbeat. Nothing here survives a
restart by design, and the TTL is what stops a killed process from parking a
slot forever.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from loguru import logger
from valkey.asyncio import Valkey

from music import keys
from music.client import PlayerClient
from music.models import LeasedBot, PoolExhaustedError, PoolSlot
from music.names import NAMES_KEY, release_nickname, roll_nickname
from music.valkey_io import decode_mapping, resolve

LEASE_KEY = keys.LEASE
SESSION_KEY = keys.SESSION
LEASE_TTL_SECONDS = keys.SESSION_TTL_SECONDS
HEARTBEAT_SECONDS = 60
MAX_BOTS = 5

# Compare-and-delete: only the holder may release a lease, so a heartbeat that
# lost a race can never delete a slot another channel has since acquired.
_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""


class BotPool:
    """Owns the player bot tokens and the Valkey leases that allocate them."""

    def __init__(
        self,
        tokens: list[str],
        valkey: Valkey,
        client_factory: Callable[[int], PlayerClient] = PlayerClient,
    ) -> None:
        if len(tokens) > MAX_BOTS:
            raise ValueError(f"At most {MAX_BOTS} music bots, got {len(tokens)}")
        self._tokens = tokens
        self._valkey = valkey
        self._client_factory = client_factory
        self._clients: dict[int, PlayerClient] = {}
        self._leases: dict[int, LeasedBot] = {}
        self._release = valkey.register_script(_RELEASE_SCRIPT)
        self._heartbeat: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    @property
    def size(self) -> int:
        return len(self._tokens)

    def client_for(self, bot_index: int) -> PlayerClient | None:
        return self._clients.get(bot_index)

    async def reset_state(self) -> None:
        """Clear every lease, session and name left by a previous process.

        Sessions never survive a restart, so anything still in Valkey at startup
        is stale by definition and would otherwise shrink the pool silently.
        """
        lease_keys = [LEASE_KEY.format(index=i) for i in range(self.size)]
        stale = [
            key
            for pattern in keys.STALE_PATTERNS
            async for key in self._valkey.scan_iter(match=pattern)
        ]
        await self._valkey.delete(*lease_keys, *stale, NAMES_KEY)
        logger.info("MusicPool: cleared {} stale session key(s)", len(stale))

    async def slots(self) -> list[PoolSlot]:
        """Current occupancy of every slot, newest state straight from Valkey."""
        values: list[Any] = await self._valkey.mget(
            [LEASE_KEY.format(index=i) for i in range(self.size)]
        )
        return [
            PoolSlot(
                bot_index=index,
                voice_channel_id=int(value) if value else None,
            )
            for index, value in enumerate(values)
        ]

    async def existing(self, voice_channel_id: int) -> LeasedBot | None:
        """The bot already serving this channel, if any."""
        raw = await resolve(
            self._valkey.hgetall(SESSION_KEY.format(voice_channel_id=voice_channel_id))
        )
        if not raw:
            return None
        data = decode_mapping(raw)
        return LeasedBot(
            bot_index=int(data["bot_index"]),
            nickname=data["nickname"],
            voice_channel_id=voice_channel_id,
        )

    async def acquire(self, voice_channel_id: int) -> LeasedBot:
        """Return the bot serving this channel, leasing a free one if needed."""
        async with self._lock:
            current = await self.existing(voice_channel_id)
            if current is not None:
                return current

            index = await self._claim_slot(voice_channel_id)
            if index is None:
                raise PoolExhaustedError(await self.slots())

            nickname: str | None = None
            try:
                nickname = await roll_nickname(self._valkey)
                client = self._client_factory(index)
                await client.launch(self._tokens[index])
            except Exception:
                # Unwind in reverse. A claimed name must go back too, or a failed
                # login would burn a nickname for the lifetime of the process.
                if nickname is not None:
                    await release_nickname(self._valkey, nickname)
                await self._release_slot(index, voice_channel_id)
                raise

            self._clients[index] = client
            lease = LeasedBot(
                bot_index=index,
                nickname=nickname,
                voice_channel_id=voice_channel_id,
            )
            self._leases[index] = lease
            session_key = SESSION_KEY.format(voice_channel_id=voice_channel_id)
            await resolve(
                self._valkey.hset(
                    session_key,
                    mapping={"bot_index": str(index), "nickname": nickname},
                )
            )
            await self._valkey.expire(session_key, LEASE_TTL_SECONDS)
            logger.info(
                "MusicPool: leased bot {} as '{}' to channel {}",
                index,
                nickname,
                voice_channel_id,
            )
            return lease

    async def release(self, voice_channel_id: int) -> None:
        """Stop the bot serving this channel and free its slot and name."""
        async with self._lock:
            lease = await self.existing(voice_channel_id)
            if lease is None:
                return

            client = self._clients.pop(lease.bot_index, None)
            if client is not None:
                await client.shutdown()
            self._leases.pop(lease.bot_index, None)

            await self._valkey.delete(*keys.session_keys(voice_channel_id))
            await release_nickname(self._valkey, lease.nickname)
            await self._release_slot(lease.bot_index, voice_channel_id)
            logger.info(
                "MusicPool: released bot {} from channel {}",
                lease.bot_index,
                voice_channel_id,
            )

    async def start_heartbeat(self) -> None:
        """Keep every held lease alive while this process is running."""
        if self._heartbeat is None:
            self._heartbeat = asyncio.create_task(
                self._refresh_loop(), name="music-lease-heartbeat"
            )

    async def shutdown(self) -> None:
        """Release everything this process holds. Called on service teardown."""
        if self._heartbeat is not None:
            self._heartbeat.cancel()
            await asyncio.gather(self._heartbeat, return_exceptions=True)
            self._heartbeat = None
        for lease in list(self._leases.values()):
            await self.release(lease.voice_channel_id)

    async def _claim_slot(self, voice_channel_id: int) -> int | None:
        for index in range(self.size):
            won = await self._valkey.set(
                LEASE_KEY.format(index=index),
                str(voice_channel_id),
                nx=True,
                ex=LEASE_TTL_SECONDS,
            )
            if won:
                return index
        return None

    async def _release_slot(self, index: int, voice_channel_id: int) -> None:
        await self._release(
            keys=[LEASE_KEY.format(index=index)], args=[str(voice_channel_id)]
        )

    async def _refresh_lease(self, lease: LeasedBot) -> None:
        # Every key belonging to a live session is refreshed together, so a
        # crashed process expires the whole session rather than leaving the
        # queue and activity feed behind with no bot attached to them.
        live = (
            LEASE_KEY.format(index=lease.bot_index),
            *keys.session_keys(lease.voice_channel_id),
        )
        for key in live:
            await self._valkey.expire(key, LEASE_TTL_SECONDS)

    async def _refresh_loop(self) -> None:
        # Self-rescheduling rather than a fixed tick: the next sleep only starts
        # once the current refresh has finished, so a slow Valkey cannot stack
        # refreshes up behind each other.
        while True:
            try:
                await asyncio.sleep(HEARTBEAT_SECONDS)
                for lease in list(self._leases.values()):
                    await self._refresh_lease(lease)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning("MusicPool: lease heartbeat failed: {}", exc)
