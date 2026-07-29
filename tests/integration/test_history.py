"""Session history against a real Valkey list.

The cap, the ordering and the TTL are Valkey semantics - LPUSH, LTRIM, EXPIRE -
so a mocked client would only assert that the mock was called. What matters
here is that the list the panel and the website both read is the same list, that
it never grows without bound, and that it dies with the session.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
import wavelink
from valkey.asyncio import Valkey

from music import keys
from music import session as session_module
from music.history import HISTORY_LIMIT, PLAYED, SKIPPED, PlayHistory
from music.models import Track
from music.session import MusicSession
from music.stats import StatsStream
from music.valkey_io import resolve
from tests.factories import make_track

pytestmark = pytest.mark.integration

CHANNEL = 4242
GUILD = 1234


class FakePlayer:
    def __init__(self) -> None:
        self.node = cast(wavelink.Node, object())
        self.playing = False
        self.position = 0

    async def play(self, playable: Any, volume: int | None = None, **_: Any) -> Any:
        self.playing = True
        return playable

    async def stop(self, *, force: bool = True) -> None:
        self.playing = False

    async def set_volume(self, value: int = 100, /) -> None:
        return None


@pytest.fixture
def player() -> FakePlayer:
    return FakePlayer()


@pytest.fixture
def session(
    valkey: Valkey, player: FakePlayer, monkeypatch: pytest.MonkeyPatch
) -> MusicSession:
    async def fake_resolve(track: Track, *, node: Any) -> tuple[Any, str]:
        return track.to_playable(), "youtube"

    monkeypatch.setattr(session_module, "resolve_playback", fake_resolve)
    return MusicSession(valkey, cast(wavelink.Player, player), CHANNEL, GUILD)


@pytest.fixture
def history(valkey: Valkey) -> PlayHistory:
    return PlayHistory(valkey, CHANNEL, StatsStream(valkey, GUILD))


async def test_a_finished_track_lands_in_the_history(session: MusicSession) -> None:
    await session.queue.add([make_track(identifier="t0")])
    await session.play_next()
    await session.advance("finished")

    entries = await session.history.recent()
    assert [entry.track.identifier for entry in entries] == ["t0"]
    assert entries[0].event == PLAYED


async def test_a_skipped_track_is_recorded_as_skipped(session: MusicSession) -> None:
    await session.queue.add([make_track(identifier="t0")])
    await session.play_next()

    await session.skip(actor_id=42)

    entries = await session.history.recent()
    assert [entry.event for entry in entries] == [SKIPPED]


async def test_the_newest_track_is_first(history: PlayHistory) -> None:
    for index in range(3):
        await history.record(make_track(identifier=f"t{index}"), PLAYED, 1000)

    entries = await history.recent()
    assert [entry.track.identifier for entry in entries] == ["t2", "t1", "t0"]


async def test_the_stored_track_carries_no_lavalink_audio(
    history: PlayHistory, valkey: Valkey
) -> None:
    # The payload is the largest thing a track holds and a re-queued track is
    # resolved at play time anyway, so keeping it would bloat the key for
    # nothing - and would put a playable handle on the web surface.
    await history.record(make_track(identifier="t0"), PLAYED, 1000)

    stored = await resolve(
        valkey.lrange(keys.HISTORY.format(voice_channel_id=CHANNEL), 0, 0)
    )
    raw = stored[0]
    assert b"encoded-t0" not in raw

    entry = (await history.recent())[0]
    assert entry.track.encoded == ""
    assert entry.track.payload == {}
    assert entry.track.title == "Zanaris Nocturne"


async def test_the_list_stops_growing_at_the_cap(history: PlayHistory) -> None:
    for index in range(HISTORY_LIMIT + 10):
        await history.record(make_track(identifier=f"t{index}"), PLAYED, 1000)

    entries = await history.recent(HISTORY_LIMIT + 10)
    assert len(entries) == HISTORY_LIMIT
    # The oldest are the ones dropped.
    assert entries[0].track.identifier == f"t{HISTORY_LIMIT + 9}"


async def test_the_history_expires_with_the_rest_of_the_session(
    history: PlayHistory, valkey: Valkey
) -> None:
    await history.record(make_track(), PLAYED, 1000)

    ttl = await valkey.ttl(keys.HISTORY.format(voice_channel_id=CHANNEL))
    assert 0 < ttl <= keys.SESSION_TTL_SECONDS


async def test_the_history_key_is_swept_with_the_session(history: PlayHistory) -> None:
    # Listed in SESSION_KEYS, so the pool's orphan sweep and its heartbeat both
    # already cover it rather than needing a second place to know about it.
    assert keys.HISTORY in keys.SESSION_KEYS
    assert keys.HISTORY.format(voice_channel_id=CHANNEL) in keys.session_keys(CHANNEL)


async def test_recording_still_emits_the_anonymous_counter(
    history: PlayHistory, valkey: Valkey
) -> None:
    await history.record(make_track(identifier="t0"), PLAYED, 1000)

    entries = await valkey.xrange(keys.EVENTS)
    assert len(entries) == 1
    assert entries[0][1][b"event"] == b"track_played"
