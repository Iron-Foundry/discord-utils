"""Guard: the web music seam matches the shared contract.

The monorepo-root fixture pins what crosses between this process and
api-backend - the session hash written here and read there, the command
published there and executed here, and the state notice. Nothing in either
repo's own suite would catch a field renamed on one side only.

Skipped when run outside the monorepo checkout (submodule-only CI).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from music import keys
from music.dispatch import MusicCommand
from music.history import SKIPPED, PlayedTrack
from music.models import Track
from music.notify import CHANGED, CLOSED
from music.state import SessionState

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"

pytestmark = pytest.mark.skipif(
    not _FIXTURES.exists(),
    reason="root fixtures/ not present (submodule-only checkout)",
)


def fixture() -> dict[str, Any]:
    return json.loads((_FIXTURES / "music_bridge.json").read_text())


def test_the_channel_names_match_the_contract() -> None:
    channels = fixture()["channels"]

    assert channels["commands"] == keys.COMMANDS
    assert channels["state"] == keys.STATE


def test_a_published_command_parses_into_the_action_it_names() -> None:
    command = MusicCommand.model_validate(fixture()["command"])

    assert command.action == "seek"
    assert command.position_ms == 90_000
    assert command.actor_id == 111222333444555666


def test_the_stored_track_parses_with_this_side_of_the_seam() -> None:
    track = Track.model_validate_json(fixture()["session_hash"]["track"])

    assert track.title == "Zanaris Nocturne"
    assert track.played_source == "youtube"
    # Both are written here and only read on the other side: api-backend cannot
    # resolve a Discord name, and the cover exists only once audio was resolved.
    assert track.artwork == "https://i.scdn.co/image/abc123"
    assert track.requester_name == "Saltis"


async def test_every_hash_field_the_contract_names_is_actually_written() -> None:
    # api-backend reads these names out of the hash. One renamed here and not
    # there reads back as a default rather than as an error.
    valkey = AsyncMock()
    state = SessionState(valkey, 555000111)

    await state.set_live(paused=False, position_ms=42_000)
    await state.set_channel(guild_id=1234567890, name="Music Lounge")
    await state.set_volume(60)
    await state.set_shuffle(False)

    written = {
        field
        for call in valkey.hset.await_args_list
        for field in call.kwargs["mapping"]
    }
    expected = set(fixture()["session_hash"]) - {
        "bot_index",
        "nickname",
        "track",
        "loop",
    }

    assert expected <= written


def test_the_history_key_is_the_one_api_backend_reads() -> None:
    # api-backend hardcodes this name rather than importing it, so a rename
    # here would leave its history endpoint reading an empty list forever.
    assert fixture()["history_key"] == keys.HISTORY


def test_a_history_entry_parses_with_this_side_of_the_seam() -> None:
    entry = PlayedTrack.model_validate_json(fixture()["history_entry"])

    assert entry.event == SKIPPED
    assert entry.track.title == "Zanaris Nocturne"


def test_a_history_entry_carries_no_playable_audio() -> None:
    # What this side writes is metadata only, which is what lets api-backend
    # hand the whole entry to a browser.
    entry = PlayedTrack.model_validate_json(fixture()["history_entry"])

    assert entry.track.encoded == ""
    assert entry.track.payload == {}


def test_the_state_notice_events_are_the_ones_the_contract_pins() -> None:
    assert fixture()["state_notice"]["event"] in {CHANGED, CLOSED}
    assert set(fixture()["state_notice"]) == {"voice_channel_id", "event"}
