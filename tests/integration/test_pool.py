"""Lease semantics against a real Valkey."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, ClassVar

import pytest
from valkey.asyncio import Valkey

from music import keys
from music.models import PoolExhaustedError
from music.names import NAMES_KEY
from music.pool import LEASE_KEY, LEASE_TTL_SECONDS, SESSION_KEY, BotPool
from music.valkey_io import resolve

pytestmark = pytest.mark.integration


class FakeClient:
    """Stands in for PlayerClient so leases can be tested without Discord."""

    instances: ClassVar[list[FakeClient]] = []

    def __init__(self, bot_index: int) -> None:
        self.bot_index = bot_index
        self.launched = False
        self.stopped = False
        FakeClient.instances.append(self)

    async def launch(self, token: str) -> None:
        self.launched = True

    async def shutdown(self) -> None:
        self.stopped = True


class FailingClient(FakeClient):
    async def launch(self, token: str) -> None:
        raise RuntimeError("login rejected")


def build_pool(
    valkey: Valkey,
    size: int = 5,
    factory: Callable[[int], Any] = FakeClient,
) -> BotPool:
    FakeClient.instances = []
    tokens = [f"token-{i}" for i in range(size)]
    return BotPool(tokens, valkey, client_factory=factory)


async def test_acquire_leases_a_slot_and_records_the_session(valkey: Valkey) -> None:
    pool = build_pool(valkey)
    lease = await pool.acquire(voice_channel_id=100)

    assert lease.bot_index == 0
    assert await valkey.get(LEASE_KEY.format(index=0)) == b"100"
    session = await resolve(valkey.hgetall(SESSION_KEY.format(voice_channel_id=100)))
    assert session[b"nickname"].decode() == lease.nickname


async def test_lease_carries_a_ttl_so_a_dead_process_frees_its_slot(
    valkey: Valkey,
) -> None:
    pool = build_pool(valkey)
    await pool.acquire(voice_channel_id=100)
    ttl = await valkey.ttl(LEASE_KEY.format(index=0))
    assert 0 < ttl <= LEASE_TTL_SECONDS


async def test_same_channel_reuses_its_bot(valkey: Valkey) -> None:
    pool = build_pool(valkey)
    first = await pool.acquire(voice_channel_id=100)
    second = await pool.acquire(voice_channel_id=100)

    assert first == second
    assert len(FakeClient.instances) == 1


async def test_concurrent_acquires_never_share_a_bot(valkey: Valkey) -> None:
    pool = build_pool(valkey)
    leases = await asyncio.gather(*(pool.acquire(200 + i) for i in range(5)))

    assert sorted(lease.bot_index for lease in leases) == [0, 1, 2, 3, 4]
    assert len({lease.voice_channel_id for lease in leases}) == 5


async def test_nicknames_are_unique_across_the_live_pool(valkey: Valkey) -> None:
    pool = build_pool(valkey)
    leases = await asyncio.gather(*(pool.acquire(300 + i) for i in range(5)))

    nicknames = {lease.nickname for lease in leases}
    assert len(nicknames) == 5
    assert await resolve(valkey.scard(NAMES_KEY)) == 5


async def test_exhaustion_reports_the_occupied_channels(valkey: Valkey) -> None:
    pool = build_pool(valkey, size=2)
    await pool.acquire(voice_channel_id=401)
    await pool.acquire(voice_channel_id=402)

    with pytest.raises(PoolExhaustedError) as caught:
        await pool.acquire(voice_channel_id=403)

    assert "<#401>" in str(caught.value)
    assert "<#402>" in str(caught.value)
    assert [slot.voice_channel_id for slot in caught.value.slots] == [401, 402]


async def test_release_frees_slot_name_and_session(valkey: Valkey) -> None:
    pool = build_pool(valkey)
    lease = await pool.acquire(voice_channel_id=500)
    await pool.release(voice_channel_id=500)

    assert await valkey.get(LEASE_KEY.format(index=lease.bot_index)) is None
    assert await resolve(valkey.exists(SESSION_KEY.format(voice_channel_id=500))) == 0
    assert await resolve(valkey.sismember(NAMES_KEY, lease.nickname)) == 0
    assert FakeClient.instances[0].stopped


async def test_released_slot_is_reusable(valkey: Valkey) -> None:
    pool = build_pool(valkey, size=1)
    await pool.acquire(voice_channel_id=600)
    await pool.release(voice_channel_id=600)
    reused = await pool.acquire(voice_channel_id=601)

    assert reused.bot_index == 0


async def test_releasing_an_unknown_channel_is_a_no_op(valkey: Valkey) -> None:
    pool = build_pool(valkey)
    await pool.release(voice_channel_id=999)
    assert await valkey.get(LEASE_KEY.format(index=0)) is None


async def test_failed_login_leaks_neither_slot_nor_nickname(valkey: Valkey) -> None:
    pool = build_pool(valkey, size=1, factory=FailingClient)

    with pytest.raises(RuntimeError, match="login rejected"):
        await pool.acquire(voice_channel_id=700)

    assert await valkey.get(LEASE_KEY.format(index=0)) is None
    assert await resolve(valkey.scard(NAMES_KEY)) == 0


async def test_reset_state_clears_everything_a_dead_process_left(
    valkey: Valkey,
) -> None:
    pool = build_pool(valkey)
    await pool.acquire(voice_channel_id=800)
    await pool.acquire(voice_channel_id=801)

    fresh = build_pool(valkey)
    await fresh.reset_state()

    assert await valkey.get(LEASE_KEY.format(index=0)) is None
    assert await resolve(valkey.exists(SESSION_KEY.format(voice_channel_id=800))) == 0
    assert await resolve(valkey.scard(NAMES_KEY)) == 0
    assert all(slot.is_free for slot in await fresh.slots())


async def test_release_only_deletes_your_own_lease(valkey: Valkey) -> None:
    # Compare-and-delete: a stale releaser must not free a slot that has since
    # been re-leased to a different channel.
    pool = build_pool(valkey, size=1)
    await pool.acquire(voice_channel_id=900)
    await valkey.set(LEASE_KEY.format(index=0), "901")

    await pool.release(voice_channel_id=900)

    assert await valkey.get(LEASE_KEY.format(index=0)) == b"901"


async def test_release_takes_the_whole_session_with_it(valkey: Valkey) -> None:
    # Queue, activity and roster all belong to the session. Leaving any of them
    # behind would shrink Valkey's usable state with every session that ends.
    pool = build_pool(valkey, size=1)
    await pool.acquire(voice_channel_id=1100)
    await _seed_session(valkey, 1100)

    await pool.release(voice_channel_id=1100)

    for key in keys.session_keys(1100):
        assert await resolve(valkey.exists(key)) == 0


async def test_reset_state_sweeps_orphaned_session_keys(valkey: Valkey) -> None:
    await _seed_session(valkey, 1200)

    await build_pool(valkey).reset_state()

    for key in keys.session_keys(1200):
        assert await resolve(valkey.exists(key)) == 0


async def test_heartbeat_refreshes_every_key_of_a_live_session(
    valkey: Valkey,
) -> None:
    pool = build_pool(valkey, size=1)
    lease = await pool.acquire(voice_channel_id=1300)
    await _seed_session(valkey, 1300)
    for key in keys.session_keys(1300):
        await valkey.expire(key, 5)

    await pool._refresh_lease(lease)

    for key in keys.session_keys(1300):
        assert await valkey.ttl(key) > 5


async def _seed_session(valkey: Valkey, voice_channel_id: int) -> None:
    await resolve(
        valkey.rpush(keys.QUEUE.format(voice_channel_id=voice_channel_id), "track")
    )
    await resolve(
        valkey.rpush(keys.ACTIVITY.format(voice_channel_id=voice_channel_id), "entry")
    )
    await resolve(
        valkey.rpush(keys.HISTORY.format(voice_channel_id=voice_channel_id), "played")
    )
    await resolve(
        valkey.sadd(keys.VOICE.format(voice_channel_id=voice_channel_id), "1")
    )
    await resolve(
        valkey.hset(
            keys.SESSION.format(voice_channel_id=voice_channel_id),
            mapping={"bot_index": "0", "nickname": "seeded"},
        )
    )


async def test_slots_reports_live_occupancy(valkey: Valkey) -> None:
    pool = build_pool(valkey, size=3)
    await pool.acquire(voice_channel_id=1000)

    slots = await pool.slots()
    assert [slot.voice_channel_id for slot in slots] == [1000, None, None]
