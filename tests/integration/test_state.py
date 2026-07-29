"""Session state, activity feed and voice roster against real Valkey."""

from __future__ import annotations

import pytest
from valkey.asyncio import Valkey

from music import keys
from music.activity import ACTIVITY_LIMIT, ActivityFeed
from music.models import LoopMode
from music.state import DEFAULT_VOLUME, MAX_VOLUME, SessionState
from music.voice import VoiceRoster
from tests.factories import make_track

pytestmark = pytest.mark.integration

CHANNEL = 777


async def test_defaults_before_anything_is_written(valkey: Valkey) -> None:
    state = SessionState(valkey, CHANNEL)

    assert await state.current() is None
    assert await state.volume() == DEFAULT_VOLUME
    assert await state.loop() is LoopMode.OFF


async def test_current_track_round_trips(valkey: Valkey) -> None:
    state = SessionState(valkey, CHANNEL)
    track = make_track()
    track.played_source = "youtube"
    await state.set_current(track)

    restored = await state.current()
    assert restored is not None
    assert restored.title == track.title
    assert restored.played_source == "youtube"


async def test_clearing_the_current_track(valkey: Valkey) -> None:
    state = SessionState(valkey, CHANNEL)
    await state.set_current(make_track())
    await state.set_current(None)

    assert await state.current() is None


async def test_volume_is_clamped_to_the_ceiling(valkey: Valkey) -> None:
    state = SessionState(valkey, CHANNEL)

    assert await state.set_volume(9000) == MAX_VOLUME
    assert await state.set_volume(-5) == 0


async def test_loop_mode_persists(valkey: Valkey) -> None:
    state = SessionState(valkey, CHANNEL)
    await state.set_loop(LoopMode.QUEUE)

    assert await state.loop() is LoopMode.QUEUE


async def test_state_writes_refresh_the_ttl(valkey: Valkey) -> None:
    state = SessionState(valkey, CHANNEL)
    await state.set_volume(50)

    ttl = await valkey.ttl(keys.SESSION.format(voice_channel_id=CHANNEL))
    assert 0 < ttl <= keys.SESSION_TTL_SECONDS


async def test_activity_is_newest_first_and_capped(valkey: Valkey) -> None:
    feed = ActivityFeed(valkey, CHANNEL)
    for index in range(ACTIVITY_LIMIT + 5):
        await feed.push(1, "queued", f"track {index}")

    entries = await feed.recent()
    assert len(entries) == ACTIVITY_LIMIT
    assert entries[0].detail == f"track {ACTIVITY_LIMIT + 4}"


async def test_activity_renders_a_relative_timestamp(valkey: Valkey) -> None:
    feed = ActivityFeed(valkey, CHANNEL)
    await feed.push(42, "skipped", "Zanaris Nocturne")

    line = (await feed.recent())[0].render()
    assert "<@42>" in line
    assert ":R>" in line


async def test_activity_records_who_acted_by_name(valkey: Valkey) -> None:
    # The panel can render a mention and let Discord resolve it. The website
    # cannot resolve anything, so the name is attached at write time.
    feed = ActivityFeed(
        valkey, CHANNEL, lambda user_id: "Saltis" if user_id == 7 else None
    )

    await feed.push(7, "queued", "Zanaris Nocturne")

    assert (await feed.recent())[0].actor_name == "Saltis"


async def test_activity_without_a_name_still_records_the_action(
    valkey: Valkey,
) -> None:
    # A member the cache cannot resolve, or a feed built without a guild at
    # all. The id is shown instead; nothing is lost but the name.
    feed = ActivityFeed(valkey, CHANNEL, lambda _user_id: None)

    await feed.push(7, "skipped", "Zanaris Nocturne")

    entry = (await feed.recent())[0]
    assert entry.actor_name == ""
    assert entry.actor_id == 7


async def test_roster_decides_who_may_control(valkey: Valkey) -> None:
    roster = VoiceRoster(valkey, CHANNEL)
    await roster.sync([11, 22])

    assert await roster.may_control(11)
    assert not await roster.may_control(33)
    assert await roster.size() == 2


async def test_roster_sync_replaces_rather_than_merges(valkey: Valkey) -> None:
    roster = VoiceRoster(valkey, CHANNEL)
    await roster.sync([11, 22])
    await roster.sync([22])

    assert not await roster.may_control(11)
    assert await roster.size() == 1


async def test_empty_roster_leaves_nobody_in_control(valkey: Valkey) -> None:
    roster = VoiceRoster(valkey, CHANNEL)
    await roster.sync([11])
    await roster.sync([])

    assert await roster.size() == 0
    assert not await roster.may_control(11)
