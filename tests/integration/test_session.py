"""Loop and transport semantics, driven off a real Valkey queue.

Lavalink itself is replaced by a fake player: what is under test is which track
gets chosen next and what the session records, not whether Lavalink can decode
audio. The queue, the state hash and the event stream are all real.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

import pytest
import wavelink
from valkey.asyncio import Valkey

from music import keys
from music import session as session_module
from music.models import LoopMode, Track
from music.naming import NameLookup
from music.session import MusicSession
from music.stats import TRACK_PLAYED, TRACK_SKIPPED
from tests.factories import make_track

pytestmark = pytest.mark.integration

CHANNEL = 999
GUILD = 1234


class FakePlayer:
    """Records what the session asked Lavalink to do."""

    def __init__(self) -> None:
        self.node = cast(wavelink.Node, object())
        self.played: list[str] = []
        self.playing = False
        self.position = 0
        self.volume: int | None = None
        self.paused: bool | None = None
        self.stopped = False

    async def play(self, playable: Any, volume: int | None = None, **_: Any) -> Any:
        self.played.append(playable.identifier)
        self.playing = True
        self.volume = volume
        return playable

    async def stop(self, *, force: bool = True) -> None:
        self.stopped = True
        self.playing = False

    async def pause(self, value: bool, /) -> None:
        self.paused = value

    async def seek(self, position: int = 0, /) -> None:
        self.position = position

    async def set_volume(self, value: int = 100, /) -> None:
        self.volume = value


@pytest.fixture
def player() -> FakePlayer:
    return FakePlayer()


@pytest.fixture
def make_session(
    valkey: Valkey, player: FakePlayer, monkeypatch: pytest.MonkeyPatch
) -> Callable[..., MusicSession]:
    """Sessions over the real Valkey, with playback resolution faked out."""

    async def fake_resolve(track: Track, *, node: Any) -> tuple[Any, str]:
        return track.to_playable(), "youtube"

    monkeypatch.setattr(session_module, "resolve_playback", fake_resolve)

    def build(names: NameLookup | None = None) -> MusicSession:
        return MusicSession(
            valkey, cast(wavelink.Player, player), CHANNEL, GUILD, names
        )

    return build


@pytest.fixture
def session(make_session: Callable[..., MusicSession]) -> MusicSession:
    return make_session()


async def test_play_next_records_where_the_audio_came_from(
    session: MusicSession, player: FakePlayer
) -> None:
    await session.queue.add([make_track(identifier="t0")])

    track = await session.play_next()
    assert track is not None
    assert player.played == ["t0"]
    # Requested from Spotify, actually streamed from YouTube.
    assert track.requested_source == "spotify"
    assert track.played_source == "youtube"


async def test_play_next_stores_the_current_track(session: MusicSession) -> None:
    await session.queue.add([make_track(identifier="t0")])
    await session.play_next()

    current = await session.state.current()
    assert current is not None
    assert current.identifier == "t0"


async def test_play_next_on_an_empty_queue_clears_the_current_track(
    session: MusicSession,
) -> None:
    await session.queue.add([make_track(identifier="t0")])
    await session.play_next()

    assert await session.play_next() is None
    assert await session.state.current() is None


async def test_advance_plays_the_next_track_when_loop_is_off(
    session: MusicSession, player: FakePlayer
) -> None:
    await session.queue.add([make_track(identifier=f"t{i}") for i in range(2)])
    await session.play_next()

    await session.advance("finished")
    assert player.played == ["t0", "t1"]
    assert await session.queue.length() == 0


async def test_advance_repeats_the_track_when_looping_a_track(
    session: MusicSession, player: FakePlayer
) -> None:
    await session.queue.add([make_track(identifier="t0"), make_track(identifier="t1")])
    await session.play_next()
    await session.state.set_loop(LoopMode.TRACK)

    await session.advance("finished")
    assert player.played == ["t0", "t0"]
    # The rest of the queue is untouched by a track loop.
    assert await session.queue.length() == 1


async def test_advance_recycles_the_track_when_looping_the_queue(
    session: MusicSession, player: FakePlayer
) -> None:
    await session.queue.add([make_track(identifier="t0"), make_track(identifier="t1")])
    await session.play_next()
    await session.state.set_loop(LoopMode.QUEUE)

    await session.advance("finished")
    assert player.played == ["t0", "t1"]
    assert [track.identifier for track in await session.queue.all()] == ["t0"]


async def test_advance_ignores_reasons_we_caused_ourselves(
    session: MusicSession, player: FakePlayer
) -> None:
    await session.queue.add([make_track(identifier=f"t{i}") for i in range(2)])
    await session.play_next()

    # "replaced" is what skip produces - it has already chosen the next track.
    assert await session.advance("replaced") is None
    assert await session.advance("stopped") is None
    assert player.played == ["t0"]


async def test_advance_emits_a_played_event(
    session: MusicSession, valkey: Valkey
) -> None:
    await session.queue.add([make_track(identifier="t0", length=1000)])
    await session.play_next()
    await session.advance("finished")

    entries = await valkey.xrange(keys.EVENTS)
    events = [_field(entry, "event") for entry in entries]
    assert TRACK_PLAYED in events


async def test_skip_plays_the_next_track_and_records_a_skip(
    session: MusicSession, player: FakePlayer, valkey: Valkey
) -> None:
    await session.queue.add([make_track(identifier=f"t{i}") for i in range(2)])
    await session.play_next()
    player.position = 5000

    await session.skip(actor_id=42)
    assert player.played == ["t0", "t1"]

    entries = await valkey.xrange(keys.EVENTS)
    skips = [entry for entry in entries if _field(entry, "event") == TRACK_SKIPPED]
    assert len(skips) == 1
    assert _field(skips[0], "listened_ms") == "5000"


async def test_skip_with_nothing_left_stops_the_player(
    session: MusicSession, player: FakePlayer
) -> None:
    await session.queue.add([make_track(identifier="t0")])
    await session.play_next()

    assert await session.skip(actor_id=42) is None
    assert player.stopped


async def test_stop_clears_the_queue_and_the_current_track(
    session: MusicSession, player: FakePlayer
) -> None:
    await session.queue.add([make_track(identifier=f"t{i}") for i in range(3)])
    await session.play_next()

    await session.stop(actor_id=42)
    assert player.stopped
    assert await session.queue.length() == 0
    assert await session.state.current() is None


async def test_volume_is_applied_to_the_player_and_remembered(
    session: MusicSession, player: FakePlayer
) -> None:
    assert await session.set_volume(42, 80) == 80
    assert player.volume == 80
    assert await session.state.volume() == 80


async def test_a_new_track_starts_at_the_stored_volume(
    session: MusicSession, player: FakePlayer
) -> None:
    await session.set_volume(42, 30)
    await session.queue.add([make_track(identifier="t0")])
    await session.play_next()

    assert player.volume == 30


async def test_transport_actions_are_written_to_the_activity_feed(
    session: MusicSession,
) -> None:
    await session.queue.add([make_track(identifier="t0")])
    await session.play_next()
    await session.pause(42, True)
    await session.set_shuffle(42, True)

    actions = [entry.action for entry in await session.activity.recent()]
    assert "shuffle" in actions
    assert "paused" in actions


async def test_shuffle_mode_draws_instead_of_taking_the_front(
    session: MusicSession,
) -> None:
    # Every track still plays exactly once; only the order changes, and the
    # queue itself keeps the order tracks were added in.
    await session.set_shuffle(42, True)
    await session.queue.add([make_track(identifier=f"t{i}") for i in range(8)])

    played = []
    while (track := await session.play_next()) is not None:
        played.append(track.identifier)

    assert sorted(played) == sorted(f"t{i}" for i in range(8))


async def test_shuffle_off_plays_in_order(session: MusicSession) -> None:
    await session.queue.add([make_track(identifier=f"t{i}") for i in range(4)])

    played = []
    while (track := await session.play_next()) is not None:
        played.append(track.identifier)

    assert played == ["t0", "t1", "t2", "t3"]


async def test_a_new_session_writes_its_modes_down(session: MusicSession) -> None:
    # api-backend reads the hash rather than calling volume()/loop(), so an
    # unwritten default reads there as zero - a volume slider pinned to 0%.
    await session.state.initialise()

    stored = await session.state.read()
    assert stored["volume"] == "60"
    assert stored["loop"] == "off"
    assert stored["shuffle"] == "0"


async def test_shuffle_survives_a_round_trip_through_valkey(
    session: MusicSession,
) -> None:
    # api-backend reads this out of the hash, so it has to be stored, not held
    # in memory on the bot.
    await session.set_shuffle(42, True)
    assert await session.state.shuffle() is True

    await session.set_shuffle(42, False)
    assert await session.state.shuffle() is False


async def test_enqueue_starts_playback_when_nothing_is_playing(
    session: MusicSession, player: FakePlayer
) -> None:
    await session.enqueue(
        [make_track(identifier="t0")], actor_id=42, label="Zanaris Nocturne"
    )

    assert player.played == ["t0"]
    entries = await session.activity.recent()
    assert [entry.action for entry in entries] == ["queued"]
    assert entries[0].detail == "Zanaris Nocturne"


async def test_enqueue_does_not_interrupt_what_is_already_playing(
    session: MusicSession, player: FakePlayer
) -> None:
    await session.queue.add([make_track(identifier="t0")])
    await session.play_next()

    await session.enqueue([make_track(identifier="t1")], actor_id=42, label="Later")

    assert player.played == ["t0"]
    assert [track.identifier for track in await session.queue.all()] == ["t1"]


async def test_jump_drops_everything_it_skipped_over(
    session: MusicSession, player: FakePlayer
) -> None:
    await session.queue.add([make_track(identifier=f"t{i}") for i in range(5)])
    await session.play_next()

    track = await session.jump(actor_id=42, index=2)
    assert track is not None
    assert player.played == ["t0", "t3"]
    assert [t.identifier for t in await session.queue.all()] == ["t4"]


async def test_jump_out_of_range_changes_nothing(
    session: MusicSession, player: FakePlayer
) -> None:
    await session.queue.add([make_track(identifier="t0")])

    assert await session.jump(actor_id=42, index=9) is None
    assert player.played == []


async def test_remove_and_move_report_the_track_they_touched(
    session: MusicSession,
) -> None:
    await session.queue.add(
        [make_track(identifier=f"t{i}", title=f"Track {i}") for i in range(3)]
    )

    assert await session.remove(42, 1) == "Track 1"
    assert await session.move(42, 1, 0) == "Track 2"
    assert [t.identifier for t in await session.queue.all()] == ["t2", "t0"]
    assert await session.remove(42, 9) is None


async def test_every_state_change_notifies_the_panel(session: MusicSession) -> None:
    # The panel is edited only from here, never on a timer, so a control that
    # forgets to notify would leave a stale panel on screen.
    calls = 0

    async def on_change() -> None:
        nonlocal calls
        calls += 1

    session.on_change = on_change
    await session.queue.add([make_track(identifier=f"t{i}") for i in range(3)])
    await session.play_next()
    await session.pause(42, True)
    await session.set_volume(42, 40)
    await session.set_loop(42, LoopMode.QUEUE)
    await session.set_shuffle(42, True)
    await session.stop(42)

    assert calls == 6


async def test_a_broken_panel_does_not_break_playback(
    session: MusicSession, player: FakePlayer
) -> None:
    async def on_change() -> None:
        raise RuntimeError("Discord is having a day")

    session.on_change = on_change
    await session.queue.add([make_track(identifier="t0")])

    await session.play_next()
    assert player.played == ["t0"]


async def test_a_track_with_no_cover_takes_one_from_the_audio_it_resolved(
    session: MusicSession,
) -> None:
    # What a saved playlist row and a web-queued track both look like: metadata
    # with no art. The resolved audio is the only place one can come from.
    bare = make_track(identifier="t0").model_copy(update={"artwork": None})
    await session.queue.add([bare])

    track = await session.play_next()

    assert track is not None
    assert track.artwork == "https://example.invalid/art.png"
    current = await session.state.current()
    assert current is not None and current.artwork == track.artwork


async def test_a_cover_the_track_arrived_with_is_not_replaced(
    session: MusicSession,
) -> None:
    # The audio resolves to a mirror on another source, whose cover is not the
    # one the user picked from.
    saved = make_track(identifier="t0").model_copy(
        update={"artwork": "https://i.scdn.co/image/saved"}
    )
    await session.queue.add([saved])

    track = await session.play_next()

    assert track is not None
    assert track.artwork == "https://i.scdn.co/image/saved"


async def test_queueing_names_the_requester_from_the_guild(
    make_session: Callable[..., MusicSession], player: FakePlayer
) -> None:
    session = make_session(lambda user_id: "Saltis" if user_id == 7 else None)
    # Already playing, so the track stays in the queue to be read back.
    player.playing = True

    await session.enqueue([make_track(requester_id=7)], actor_id=7, label="one")

    assert [row.requester_name for row in await session.queue.all()] == ["Saltis"]


async def test_an_unnameable_requester_still_queues(
    make_session: Callable[..., MusicSession], player: FakePlayer
) -> None:
    session = make_session(lambda _user_id: None)
    player.playing = True

    await session.enqueue([make_track(requester_id=7)], actor_id=7, label="one")

    assert [row.requester_name for row in await session.queue.all()] == [""]


def _field(entry: Any, name: str) -> str:
    _, fields = entry
    value = fields[name.encode()]
    return value.decode() if isinstance(value, bytes) else value
