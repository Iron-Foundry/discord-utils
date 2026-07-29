"""Web commands: what they become, and what they are refused for.

The transport itself is already covered elsewhere, so what is asserted here is
the seam - that an intent published by the website reaches exactly the session
call it names, and that nothing runs for someone who is not in the channel.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from music import keys
from music.bridge import CommandBridge
from music.dispatch import CommandError, MusicCommand, apply
from music.models import LoopMode
from music.notify import (
    CHANGED,
    CLOSED,
    StateKeepalive,
    publish_closed,
    publish_state,
)
from music.playlists import PlaylistDetail
from music.queue import QueueFullError

CHANNEL_ID = 555000111
ACTOR_ID = 111222333444555666

PLAYLIST: dict[str, Any] = {
    "id": 4,
    "owner_discord_id": ACTOR_ID,
    "name": "Slayer Tunes",
    "is_public": False,
    "track_count": 1,
    "tracks": [
        {
            "source": "spotify",
            "identifier": "abc123",
            "title": "Zanaris Nocturne",
            "author": "Barbarian Assault",
            "duration_ms": 180_000,
            "isrc": "USABC1234567",
            "uri": "https://open.spotify.com/track/abc123",
            "position": 0,
        }
    ],
}


def command(action: str, **fields: Any) -> MusicCommand:
    return MusicCommand(
        voice_channel_id=CHANNEL_ID, actor_id=ACTOR_ID, action=action, **fields
    )


@pytest.mark.parametrize(
    ("action", "fields", "call", "expected"),
    [
        ("pause", {"paused": True}, "pause", (ACTOR_ID, True)),
        ("pause", {"paused": False}, "pause", (ACTOR_ID, False)),
        ("skip", {}, "skip", (ACTOR_ID,)),
        ("stop", {}, "stop", (ACTOR_ID,)),
        ("shuffle", {"shuffle": True}, "set_shuffle", (ACTOR_ID, True)),
        ("shuffle", {"shuffle": False}, "set_shuffle", (ACTOR_ID, False)),
        ("seek", {"position_ms": 90_000}, "seek", (ACTOR_ID, 90_000)),
        ("volume", {"volume": 40}, "set_volume", (ACTOR_ID, 40)),
        ("remove", {"index": 3}, "remove", (ACTOR_ID, 3)),
        ("jump", {"index": 2}, "jump", (ACTOR_ID, 2)),
        ("move", {"index": 1, "destination": 4}, "move", (ACTOR_ID, 1, 4)),
    ],
)
async def test_each_action_reaches_the_transport_call_it_names(
    action: str, fields: dict[str, Any], call: str, expected: tuple[Any, ...]
) -> None:
    session = AsyncMock()
    await apply(command(action, **fields), session)

    getattr(session, call).assert_awaited_once_with(*expected)


async def test_loop_arrives_as_the_mode_it_named() -> None:
    session = AsyncMock()
    await apply(command("loop", loop=LoopMode.QUEUE), session)

    session.set_loop.assert_awaited_once_with(ACTOR_ID, LoopMode.QUEUE)


@pytest.mark.parametrize(
    ("action", "fields"),
    [
        ("seek", {}),
        ("volume", {}),
        ("loop", {}),
        ("remove", {}),
        ("move", {"index": 1}),
        ("shuffle", {}),
        ("load_playlist", {}),
        ("add", {}),
    ],
)
async def test_an_action_missing_its_argument_never_touches_the_session(
    action: str, fields: dict[str, Any]
) -> None:
    session = AsyncMock()
    with pytest.raises(CommandError):
        await apply(command(action, **fields), session)


async def test_an_unknown_action_is_refused() -> None:
    with pytest.raises(CommandError, match="Unknown"):
        await apply(command("self_destruct"), AsyncMock())


async def test_a_playlist_load_queues_every_saved_track() -> None:
    session = AsyncMock()
    playlists = AsyncMock()
    playlists.detail.return_value = PlaylistDetail.model_validate(PLAYLIST)

    await apply(command("load_playlist", playlist_id=4), session, playlists)

    playlists.detail.assert_awaited_once_with(ACTOR_ID, 4)
    queued = session.enqueue.await_args.args[0]
    assert [track.title for track in queued] == ["Zanaris Nocturne"]
    assert session.enqueue.await_args.kwargs["label"] == "Slayer Tunes"


async def test_added_tracks_are_queued_without_a_search() -> None:
    session = AsyncMock()
    row = PLAYLIST["tracks"][0]

    await apply(command("add", tracks=[row, {**row, "title": "Sea Shanty 2"}]), session)

    queued = session.enqueue.await_args.args[0]
    assert [track.title for track in queued] == ["Zanaris Nocturne", "Sea Shanty 2"]
    # No Lavalink payload: the audio is looked up when each one plays, which is
    # the same path a saved playlist row takes.
    assert all(not track.is_playable for track in queued)
    assert all(track.requester_id == ACTOR_ID for track in queued)


async def test_one_added_track_is_named_in_the_activity_feed() -> None:
    session = AsyncMock()
    await apply(command("add", tracks=[PLAYLIST["tracks"][0]]), session)

    assert session.enqueue.await_args.kwargs["label"] == "Zanaris Nocturne"


async def test_several_added_tracks_are_counted_instead() -> None:
    session = AsyncMock()
    rows = [PLAYLIST["tracks"][0]] * 3
    await apply(command("add", tracks=rows), session)

    assert session.enqueue.await_args.kwargs["label"] == "3 tracks"


async def test_a_full_queue_refuses_an_add_with_its_own_message() -> None:
    session = AsyncMock()
    session.enqueue.side_effect = QueueFullError("Queue holds 500 of 500 tracks")

    with pytest.raises(CommandError, match="500"):
        await apply(command("add", tracks=[PLAYLIST["tracks"][0]]), session)


async def test_a_playlist_load_with_no_client_is_refused() -> None:
    with pytest.raises(CommandError, match="not configured"):
        await apply(command("load_playlist", playlist_id=4), AsyncMock(), None)


def build_bridge(*, allowed: bool, session: Any) -> tuple[CommandBridge, MagicMock]:
    service = MagicMock()
    service.session.return_value = session
    service.may_control = AsyncMock(return_value=allowed)
    service.playlists = None
    return CommandBridge("redis://unused", service), service


async def test_a_command_from_someone_not_in_the_channel_does_nothing() -> None:
    session = AsyncMock()
    bridge, _ = build_bridge(allowed=False, session=session)

    await bridge.handle(command("skip").model_dump_json())

    session.skip.assert_not_awaited()


async def test_a_command_for_a_channel_this_process_does_not_own_is_ignored() -> None:
    bridge, service = build_bridge(allowed=True, session=None)

    await bridge.handle(command("skip").model_dump_json())

    service.may_control.assert_not_awaited()


async def test_an_authorised_command_runs() -> None:
    session = AsyncMock()
    bridge, _ = build_bridge(allowed=True, session=session)

    await bridge.handle(command("skip").model_dump_json())

    session.skip.assert_awaited_once_with(ACTOR_ID)


async def test_unreadable_json_never_reaches_a_session() -> None:
    session = AsyncMock()
    bridge, service = build_bridge(allowed=True, session=session)

    await bridge.handle("{not json")

    service.session.assert_not_called()


async def test_a_refused_command_does_not_take_the_bridge_down() -> None:
    session = AsyncMock()
    session.seek.side_effect = RuntimeError("lavalink is gone")
    bridge, _ = build_bridge(allowed=True, session=session)

    await bridge.handle(command("seek", position_ms=1).model_dump_json())


async def test_a_state_notice_records_what_only_the_player_knows() -> None:
    valkey = AsyncMock()
    session = AsyncMock()
    session.voice_channel_id = CHANNEL_ID
    session.player.paused = True
    session.player.position = 42_000

    await publish_state(valkey, session)

    session.state.set_live.assert_awaited_once_with(paused=True, position_ms=42_000)
    channel, payload = valkey.publish.await_args.args
    assert channel == keys.STATE
    assert json.loads(payload) == {
        "voice_channel_id": CHANNEL_ID,
        "event": CHANGED,
    }


async def test_a_closed_session_is_announced() -> None:
    valkey = AsyncMock()
    await publish_closed(valkey, CHANNEL_ID)

    payload = json.loads(valkey.publish.await_args.args[1])
    assert payload == {"voice_channel_id": CHANNEL_ID, "event": CLOSED}


def live_session(channel_id: int) -> AsyncMock:
    session = AsyncMock()
    session.voice_channel_id = channel_id
    session.player.paused = False
    session.player.position = 1_000
    return session


async def test_the_keepalive_re_announces_every_live_session() -> None:
    # A killed bot publishes no closing notice, so a watcher can only tell a
    # quiet session from a dead one by whether these keep arriving.
    valkey = AsyncMock()
    sessions = [live_session(1), live_session(2)]
    keepalive = StateKeepalive(valkey, lambda: sessions)

    await keepalive.round()

    announced = [
        json.loads(call.args[1])["voice_channel_id"]
        for call in valkey.publish.await_args_list
    ]
    assert announced == [1, 2]


async def test_the_keepalive_refreshes_the_stored_position() -> None:
    # Also what keeps a browser's extrapolated progress bar from drifting on a
    # long track.
    valkey = AsyncMock()
    session = live_session(1)
    await StateKeepalive(valkey, lambda: [session]).round()

    session.state.set_live.assert_awaited_once_with(paused=False, position_ms=1_000)


async def test_the_keepalive_announces_nothing_when_nothing_is_live() -> None:
    valkey = AsyncMock()
    await StateKeepalive(valkey, list).round()

    valkey.publish.assert_not_awaited()


async def test_a_valkey_outage_never_takes_playback_with_it() -> None:
    valkey = AsyncMock()
    valkey.publish.side_effect = RuntimeError("valkey is gone")

    await publish_closed(valkey, CHANNEL_ID)
