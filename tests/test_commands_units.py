"""The music command surface: names, options, help, and tree registration."""

from __future__ import annotations

from typing import Any, cast

import discord
import pytest
from discord import app_commands

from command_infra.help_registry import HelpRegistry
from music.commands.playback import SOURCE_CHOICES, _queued_message
from music.commands.registry import (
    HELP_ENTRIES,
    build_commands,
    register,
    register_help,
)
from music.commands.resolver import caller_channel
from music.resolve import SOURCE_PREFIXES, SearchResult
from music.service import MusicService
from music.state import MAX_VOLUME
from tests.factories import make_track

EXPECTED = {
    "play",
    "pause",
    "resume",
    "skip",
    "stop",
    "seek",
    "queue",
    "nowplaying",
    "remove",
    "shuffle",
    "loop",
    "volume",
    "playlist",
}


def service() -> MusicService:
    return cast(MusicService, object())


def commands() -> list[app_commands.Command[Any, Any, Any]]:
    return build_commands(service())


def test_every_designed_command_exists() -> None:
    assert {command.name for command in commands()} == EXPECTED


def test_command_names_are_unique() -> None:
    names = [command.name for command in commands()]
    assert len(names) == len(set(names))


def test_every_command_describes_itself() -> None:
    assert all(command.description for command in commands())


def test_commands_register_onto_a_real_tree() -> None:
    # Catches duplicate names and malformed option schemas, which only surface
    # at registration time.
    client = discord.Client(intents=discord.Intents.none())
    tree = app_commands.CommandTree(client)
    guild = discord.Object(id=1)
    registry = HelpRegistry()

    register(service(), tree, cast(discord.Guild, guild), registry)

    assert {command.name for command in tree.get_commands(guild=guild)} == EXPECTED


def test_help_lists_exactly_the_commands_that_exist() -> None:
    # Help drifting from the command set is silent, so it is asserted.
    registry = HelpRegistry()
    register_help(registry)
    group = registry.get_group("music")
    assert group is not None

    listed = {entry.name.split()[0].removeprefix("/") for entry in group.commands}
    assert listed == EXPECTED
    assert len(group.commands) == len(HELP_ENTRIES)


def test_music_commands_are_open_to_everyone_in_the_channel() -> None:
    registry = HelpRegistry()
    register_help(registry)
    group = registry.get_group("music")
    assert group is not None
    assert {entry.access for entry in group.commands} == {"Member"}


def test_play_offers_every_search_source() -> None:
    assert {choice.value for choice in SOURCE_CHOICES} == set(SOURCE_PREFIXES)


def test_volume_is_bounded_by_the_same_ceiling_the_session_uses() -> None:
    volume = next(c for c in commands() if c.name == "volume")
    percent = volume._params["percent"]
    assert percent.max_value == MAX_VOLUME
    assert percent.min_value == 0


def test_seek_takes_a_free_text_position() -> None:
    seek = next(c for c in commands() if c.name == "seek")
    assert "position" in seek._params


def test_queued_message_names_the_playlist_when_there_is_one() -> None:
    tracks = [make_track(identifier=f"t{i}") for i in range(30)]
    result = SearchResult(tracks=tracks, playlist="Barbarian Anthems")
    assert _queued_message(result) == (
        "Queued **30** tracks from **Barbarian Anthems**."
    )


def test_queued_message_names_the_track_otherwise() -> None:
    assert "Zanaris Nocturne" in _queued_message(SearchResult(tracks=[make_track()]))


@pytest.mark.parametrize("voice", [None, "stage"])
def test_caller_channel_ignores_anything_that_is_not_a_voice_channel(
    voice: str | None,
) -> None:
    member = cast(Any, _FakeMember(voice))
    interaction = cast(discord.Interaction, _FakeInteraction(member))
    assert caller_channel(interaction) is None


class _FakeInteraction:
    def __init__(self, user: Any) -> None:
        self.user = user


class _FakeMember:
    def __init__(self, voice: str | None) -> None:
        self.voice = _FakeVoiceState() if voice else None


class _FakeVoiceState:
    channel = "not a voice channel"
