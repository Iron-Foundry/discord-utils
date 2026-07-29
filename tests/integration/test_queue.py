"""Queue behaviour against a real Valkey list."""

from __future__ import annotations

import pytest
from valkey.asyncio import Valkey

from music import keys
from music.queue import MAX_QUEUE_LENGTH, QueueFullError, TrackQueue
from tests.factories import make_track

pytestmark = pytest.mark.integration

CHANNEL = 555


def queue(valkey: Valkey) -> TrackQueue:
    return TrackQueue(valkey, CHANNEL)


async def test_add_then_pop_is_first_in_first_out(valkey: Valkey) -> None:
    q = queue(valkey)
    await q.add([make_track(identifier=f"t{i}") for i in range(3)])

    assert await q.length() == 3
    assert (await q.pop()).identifier == "t0"  # type: ignore[union-attr]
    assert (await q.pop()).identifier == "t1"  # type: ignore[union-attr]


async def test_pop_on_an_empty_queue_returns_none(valkey: Valkey) -> None:
    assert await queue(valkey).pop() is None


async def test_add_next_jumps_the_line(valkey: Valkey) -> None:
    q = queue(valkey)
    await q.add([make_track(identifier="later")])
    await q.add_next(make_track(identifier="sooner"))

    assert (await q.pop()).identifier == "sooner"  # type: ignore[union-attr]


async def test_peek_does_not_consume(valkey: Valkey) -> None:
    q = queue(valkey)
    await q.add([make_track(identifier=f"t{i}") for i in range(5)])

    peeked = await q.peek(2)
    assert [track.identifier for track in peeked] == ["t0", "t1"]
    assert await q.length() == 5


async def test_remove_drops_only_that_track(valkey: Valkey) -> None:
    q = queue(valkey)
    await q.add([make_track(identifier=f"t{i}") for i in range(3)])

    removed = await q.remove(1)
    assert removed is not None
    assert removed.identifier == "t1"
    assert [track.identifier for track in await q.all()] == ["t0", "t2"]


async def test_remove_out_of_range_changes_nothing(valkey: Valkey) -> None:
    q = queue(valkey)
    await q.add([make_track(identifier="only")])

    assert await q.remove(9) is None
    assert await q.length() == 1


async def test_move_reorders_without_losing_tracks(valkey: Valkey) -> None:
    q = queue(valkey)
    await q.add([make_track(identifier=f"t{i}") for i in range(4)])

    await q.move(3, 0)
    assert [track.identifier for track in await q.all()] == ["t3", "t0", "t1", "t2"]


async def test_a_random_draw_takes_exactly_one_track(valkey: Valkey) -> None:
    q = queue(valkey)
    await q.add([make_track(identifier=f"t{i}") for i in range(10)])

    drawn = await q.pop_random()

    assert drawn is not None
    left = {track.identifier for track in await q.all()}
    assert len(left) == 9
    assert drawn.identifier not in left


async def test_draining_at_random_yields_every_track_once(valkey: Valkey) -> None:
    # Shuffle mode draws rather than reorders, so nothing may be played twice or
    # skipped entirely on the way through the queue.
    q = queue(valkey)
    await q.add([make_track(identifier=f"t{i}") for i in range(10)])

    drawn = []
    while (track := await q.pop_random()) is not None:
        drawn.append(track.identifier)

    assert sorted(drawn) == sorted(f"t{i}" for i in range(10))


async def test_a_random_draw_from_an_empty_queue_is_none(valkey: Valkey) -> None:
    assert await queue(valkey).pop_random() is None


async def test_duplicate_tracks_survive_a_rewrite(valkey: Valkey) -> None:
    # A list rewrite is used precisely because LSET-plus-LREM would delete both
    # copies of an identical track.
    q = queue(valkey)
    await q.add([make_track(identifier="same") for _ in range(3)])

    await q.remove(0)
    assert await q.length() == 2


async def test_remaining_ms_sums_the_queue(valkey: Valkey) -> None:
    q = queue(valkey)
    await q.add([make_track(identifier=f"t{i}", length=1000) for i in range(3)])

    assert await q.remaining_ms() == 3000


async def test_queue_carries_a_ttl(valkey: Valkey) -> None:
    q = queue(valkey)
    await q.add([make_track()])

    ttl = await valkey.ttl(keys.QUEUE.format(voice_channel_id=CHANNEL))
    assert 0 < ttl <= keys.SESSION_TTL_SECONDS


async def test_queue_refuses_to_grow_past_the_cap(valkey: Valkey) -> None:
    q = queue(valkey)
    await q.add([make_track(identifier=f"t{i}") for i in range(MAX_QUEUE_LENGTH)])

    with pytest.raises(QueueFullError):
        await q.add([make_track(identifier="one-too-many")])


async def test_clear_empties_the_queue(valkey: Valkey) -> None:
    q = queue(valkey)
    await q.add([make_track()])
    await q.clear()

    assert await q.length() == 0
