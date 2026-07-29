"""Voice state changes, and what the web learns from them.

Who is in the channel is who may control it, so a join or a leave is a state
change like any other. If it never reaches the web, someone who joins after
opening the page stays locked out of a session they are sitting in.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord

from music.events import register

CHANNEL_ID = 555000111


def member(user_id: int, *, bot: bool = False) -> MagicMock:
    person = MagicMock(spec=discord.Member)
    person.id = user_id
    person.bot = bot
    return person


def channel(*members: MagicMock) -> MagicMock:
    voice = MagicMock(spec=discord.VoiceChannel)
    voice.id = CHANNEL_ID
    voice.members = list(members)
    return voice


def fake_valkey() -> tuple[AsyncMock, MagicMock]:
    """A Valkey whose `pipeline()` behaves like the async context manager it is."""
    valkey = AsyncMock()
    pipe = MagicMock()
    pipe.execute = AsyncMock()
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=pipe)
    manager.__aexit__ = AsyncMock(return_value=False)
    valkey.pipeline = MagicMock(return_value=manager)
    return valkey, pipe


def wire(*, session: Any) -> tuple[Any, MagicMock, MagicMock]:
    """Register the listeners and hand back the voice one, the service and the pipe."""
    valkey, pipe = fake_valkey()
    service = MagicMock()
    service.valkey = valkey
    service.session.return_value = session
    service.leave = AsyncMock()

    listeners: dict[str, Any] = {}
    client = MagicMock()
    client.add_listener = lambda fn, name: listeners.__setitem__(name, fn)
    register(service, client)
    return listeners["on_voice_state_update"], service, pipe


def live_session() -> AsyncMock:
    session = AsyncMock()
    session.voice_channel_id = CHANNEL_ID
    session.player.paused = False
    session.player.position = 0
    return session


def published(service: MagicMock) -> list[dict[str, Any]]:
    return [json.loads(call.args[1]) for call in service.valkey.publish.await_args_list]


CHANGED = [{"voice_channel_id": CHANNEL_ID, "event": "changed"}]


async def test_someone_joining_is_pushed_to_the_web() -> None:
    on_voice_state, service, pipe = wire(session=live_session())
    joined = channel(member(1), member(2))

    await on_voice_state(member(2), MagicMock(channel=None), MagicMock(channel=joined))

    pipe.sadd.assert_called_once_with(f"music:voice:{CHANNEL_ID}", 1, 2)
    assert published(service) == CHANGED


async def test_someone_leaving_is_pushed_to_the_web() -> None:
    # One human left, so the session lives on and the roster just shrinks.
    on_voice_state, service, pipe = wire(session=live_session())
    remaining = channel(member(1))

    await on_voice_state(
        member(2), MagicMock(channel=remaining), MagicMock(channel=None)
    )

    pipe.sadd.assert_called_once_with(f"music:voice:{CHANNEL_ID}", 1)
    assert published(service) == CHANGED


async def test_a_bot_joining_changes_nothing() -> None:
    on_voice_state, service, pipe = wire(session=live_session())
    joined = channel(member(1))

    await on_voice_state(
        member(9, bot=True), MagicMock(channel=None), MagicMock(channel=joined)
    )

    pipe.sadd.assert_not_called()
    assert published(service) == []


async def test_the_last_human_leaving_ends_the_session_instead() -> None:
    # A deserted channel is torn down, and closing publishes its own notice, so
    # announcing a change here too would contradict it.
    on_voice_state, service, _ = wire(session=live_session())
    empty = channel(member(9, bot=True))

    await on_voice_state(member(1), MagicMock(channel=empty), MagicMock(channel=None))

    service.leave.assert_awaited_once_with(CHANNEL_ID)
    assert published(service) == []


async def test_a_channel_with_no_session_is_left_alone() -> None:
    on_voice_state, service, pipe = wire(session=None)

    await on_voice_state(
        member(1), MagicMock(channel=None), MagicMock(channel=channel(member(1)))
    )

    pipe.sadd.assert_not_called()
    assert published(service) == []
