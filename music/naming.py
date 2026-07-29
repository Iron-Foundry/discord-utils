"""Naming the person behind a Discord id.

The website is given the name rather than left to resolve it. A snowflake is
meaningless to a browser, api-backend only knows the people who have logged
into the site, and neither of them can see a per-server nickname at all. This
process can: it holds the guild, so the name is attached once, where it is
known, and travels with the track from then on.

The lookup is deliberately cache-only. Queueing a playlist would otherwise
become one Discord request per track, and a name that cannot be resolved is not
worth blocking playback for - the id is shown instead.
"""

from __future__ import annotations

from collections.abc import Callable

import discord

from music.models import Track

NameLookup = Callable[[int], str | None]


def guild_lookup(guild: discord.Guild) -> NameLookup:
    """Name ids the way this server shows them: nickname, else display name."""

    def lookup(user_id: int) -> str | None:
        member = guild.get_member(user_id)
        return member.display_name if member is not None else None

    return lookup


def stamp_requesters(tracks: list[Track], lookup: NameLookup | None) -> None:
    """Name whoever asked for each track, skipping those already named.

    Every queued track passes through here exactly once, whichever surface it
    came from, so this is the single place a name is attached. Requeueing from
    the history clears the name along with the id, because that track is
    credited to whoever pressed the button rather than to who first asked.
    """
    if lookup is None:
        return
    for track in tracks:
        if track.requester_name:
            continue
        track.requester_name = lookup(track.requester_id) or ""
