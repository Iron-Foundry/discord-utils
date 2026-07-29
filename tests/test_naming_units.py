"""Naming the requester behind a queued track.

The lookup is the only thing standing between the website and a raw snowflake,
so what matters here is that it fires once per track, never overwrites a name
already attached, and never fails a queue when a member cannot be resolved.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from music.naming import guild_lookup, stamp_requesters
from tests.factories import make_track


def guild_with(**members: int) -> MagicMock:
    """A guild whose cache holds exactly the given display_name -> id pairs."""
    by_id = {user_id: name for name, user_id in members.items()}
    guild = MagicMock()
    guild.get_member.side_effect = lambda user_id: (
        MagicMock(display_name=by_id[user_id]) if user_id in by_id else None
    )
    return guild


def test_a_queued_track_is_named_from_the_guild() -> None:
    tracks = [make_track(requester_id=7)]

    stamp_requesters(tracks, guild_lookup(guild_with(Saltis=7)))

    assert tracks[0].requester_name == "Saltis"


def test_a_member_the_cache_does_not_hold_leaves_the_name_empty() -> None:
    # The id is shown instead. Blocking a queue on a name would be worse.
    tracks = [make_track(requester_id=7)]

    stamp_requesters(tracks, guild_lookup(guild_with(Someone=99)))

    assert tracks[0].requester_name == ""


def test_a_name_already_attached_is_left_alone() -> None:
    tracks = [make_track(requester_id=7)]
    tracks[0].requester_name = "Named Earlier"

    stamp_requesters(tracks, guild_lookup(guild_with(Saltis=7)))

    assert tracks[0].requester_name == "Named Earlier"


def test_without_a_lookup_nothing_is_named_and_nothing_raises() -> None:
    # Sessions built without a guild - every test fixture in this suite - queue
    # exactly as they did before names existed.
    tracks = [make_track(requester_id=7)]

    stamp_requesters(tracks, None)

    assert tracks[0].requester_name == ""


def test_each_track_is_resolved_for_its_own_requester() -> None:
    tracks = [make_track(requester_id=7), make_track(requester_id=8)]

    stamp_requesters(tracks, guild_lookup(guild_with(Saltis=7, Someone=8)))

    assert [track.requester_name for track in tracks] == ["Saltis", "Someone"]
