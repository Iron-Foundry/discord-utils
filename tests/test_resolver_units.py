"""How a command gets from an interaction to the session it may act on.

This is the authorisation path: the channel comes from the caller's own voice
state, so resolving one at all is what proves they are allowed to act.
"""

from __future__ import annotations

from typing import Any, cast

import discord
import pytest

from music.commands.resolver import (
    NOT_IN_VOICE,
    NOTHING_PLAYING,
    caller_channel,
    existing_session,
    open_session,
)
from music.models import PoolExhaustedError, PoolSlot
from music.service import MusicService


class FakeFollowup:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, *, view: Any, ephemeral: bool = False) -> None:
        self.sent.append(_text_of(view))


class FakeInteraction:
    def __init__(self, channel: Any = None) -> None:
        self.user = _member(channel)
        self.followup = FakeFollowup()


class FakeService:
    def __init__(
        self, session: Any = None, joins: Any = None, error: Exception | None = None
    ) -> None:
        self._session = session
        self._joins = joins
        self._error = error
        self.joined = False

    def session(self, voice_channel_id: int) -> Any:
        return self._session

    async def join(self, channel: Any) -> Any:
        self.joined = True
        if self._error is not None:
            raise self._error
        return self._joins


def channel(channel_id: int = 5) -> discord.VoiceChannel:
    fake = cast(Any, object.__new__(discord.VoiceChannel))
    fake.id = channel_id
    return fake


async def test_a_caller_outside_voice_is_told_to_join() -> None:
    interaction = FakeInteraction()

    result = await existing_session(
        _as_interaction(interaction), _as_service(FakeService())
    )

    assert result is None
    assert interaction.followup.sent == [NOT_IN_VOICE]


async def test_a_channel_with_no_session_says_so() -> None:
    interaction = FakeInteraction(channel())

    result = await existing_session(
        _as_interaction(interaction), _as_service(FakeService())
    )

    assert result is None
    assert interaction.followup.sent == [NOTHING_PLAYING]


async def test_an_existing_session_is_returned() -> None:
    sentinel = object()
    interaction = FakeInteraction(channel())

    result = await existing_session(
        _as_interaction(interaction), _as_service(FakeService(session=sentinel))
    )

    assert result is sentinel
    assert interaction.followup.sent == []


async def test_open_session_reuses_rather_than_leasing_a_second_bot() -> None:
    sentinel = object()
    service = FakeService(session=sentinel)

    result = await open_session(
        _as_interaction(FakeInteraction(channel())), _as_service(service)
    )

    assert result is sentinel
    assert not service.joined


async def test_open_session_starts_one_when_there_is_none() -> None:
    sentinel = object()
    service = FakeService(joins=sentinel)

    result = await open_session(
        _as_interaction(FakeInteraction(channel())), _as_service(service)
    )

    assert result is sentinel
    assert service.joined


async def test_pool_exhaustion_names_the_busy_channels() -> None:
    error = PoolExhaustedError([PoolSlot(bot_index=0, voice_channel_id=77)])
    interaction = FakeInteraction(channel())

    result = await open_session(
        _as_interaction(interaction), _as_service(FakeService(error=error))
    )

    assert result is None
    assert "<#77>" in interaction.followup.sent[0]


async def test_a_channel_the_bot_cannot_see_is_reported_verbatim() -> None:
    error = RuntimeError("Music bot 0 cannot see channel 5")
    interaction = FakeInteraction(channel())

    result = await open_session(
        _as_interaction(interaction), _as_service(FakeService(error=error))
    )

    assert result is None
    assert interaction.followup.sent == [str(error)]


@pytest.mark.parametrize("connected", [True, False])
def test_caller_channel_needs_a_real_voice_channel(connected: bool) -> None:
    interaction = FakeInteraction(channel() if connected else None)
    found = caller_channel(_as_interaction(interaction))
    assert (found is not None) is connected


class _Member(discord.Member):
    """A real Member subclass, because `caller_channel` isinstance-checks it.

    `Member.voice` is a read-only property backed by the guild's voice state
    cache, so it is overridden rather than assigned.
    """

    def __init__(self, voice_channel: Any) -> None:
        self._voice_channel = voice_channel

    @property
    def voice(self) -> Any:
        if self._voice_channel is None:
            return None
        return _VoiceState(self._voice_channel)


class _VoiceState:
    def __init__(self, channel: Any) -> None:
        self.channel = channel


def _member(voice_channel: Any) -> discord.Member:
    return _Member(voice_channel)


def _text_of(view: discord.ui.LayoutView) -> str:
    return "".join(
        item.content
        for item in view.walk_children()
        if isinstance(item, discord.ui.TextDisplay)
    )


def _as_interaction(fake: FakeInteraction) -> discord.Interaction:
    return cast(discord.Interaction, fake)


def _as_service(fake: FakeService) -> MusicService:
    return cast(MusicService, fake)
