"""Text and colour for the panel.

Kept apart from the components so the wording can be asserted in a test without
building a view, and so the 4000 character budget has one place to be reasoned
about.
"""

from __future__ import annotations

import discord

from music.history import SKIPPED, PlayedTrack
from music.models import LoopMode, Track
from music.playlists import PlaylistSummary
from music.views.snapshot import UPCOMING_SHOWN, PanelSnapshot

# Each source gets its own accent so the panel shows at a glance where the
# audio came from, which is the point of tracking played_source at all.
SOURCE_COLOURS = {
    "spotify": 0x1DB954,
    "youtube": 0xFF0000,
    "soundcloud": 0xFF5500,
}
DEFAULT_COLOUR = 0x5865F2

LOOP_LABELS = {
    LoopMode.OFF: "Loop off",
    LoopMode.TRACK: "Loop track",
    LoopMode.QUEUE: "Loop queue",
}

TITLE_LIMIT = 80


def duration(milliseconds: int) -> str:
    """`4:07`, or `1:02:33` once it passes an hour."""
    seconds = max(0, milliseconds) // 1000
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def truncate(text: str, limit: int = TITLE_LIMIT) -> str:
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def accent_colour(snapshot: PanelSnapshot) -> discord.Colour:
    """The colour of the source the audio actually came from."""
    if snapshot.current is None:
        return discord.Colour(DEFAULT_COLOUR)
    source = snapshot.current.played_source or snapshot.current.source
    return discord.Colour(SOURCE_COLOURS.get(source, DEFAULT_COLOUR))


def now_playing(snapshot: PanelSnapshot) -> str:
    """The header block: what is playing, who asked for it, when it ends."""
    track = snapshot.current
    if track is None:
        return "### Nothing playing\nQueue something to get started."

    state = "Paused" if snapshot.paused else "Now playing"
    lines = [
        f"### {state}",
        f"**{truncate(track.title)}**",
        f"-# {truncate(track.author, 60)}",
        f"Requested by <@{track.requester_id}> · {_source_line(track)}",
    ]
    if track.is_stream:
        lines.append("Live stream")
    elif snapshot.ends_at is not None:
        lines.append(
            f"{duration(track.length_ms)} · ends <t:{int(snapshot.ends_at.timestamp())}:R>"
        )
    return "\n".join(lines)


def up_next(snapshot: PanelSnapshot) -> str:
    """The queue summary: the next few tracks and what is left after them."""
    if not snapshot.upcoming:
        return "-# Nothing queued."

    lines = [
        f"{index}. {truncate(track.title, 60)} · -# {duration(track.length_ms)}"
        for index, track in enumerate(snapshot.upcoming, start=1)
    ]
    lines.append(
        f"-# {snapshot.queue_length} track{'s' if snapshot.queue_length != 1 else ''}"
        f", {duration(snapshot.remaining_ms)} remaining"
    )
    return "\n".join(lines)


def status_line(snapshot: PanelSnapshot) -> str:
    """The modes in force, which are the ones the buttons above do not show."""
    shuffle = "Shuffle on" if snapshot.shuffle else "Shuffle off"
    return f"-# {LOOP_LABELS[snapshot.loop]} · {shuffle} · Volume {snapshot.volume}%"


def history_line(number: int, entry: PlayedTrack) -> str:
    """One already-played track: what it was, how long, and how it ended.

    The timestamp is a Discord relative one, so the list ages in the client
    rather than the view being rebuilt to keep it honest.
    """
    stamp = int(entry.at.timestamp())
    ending = " · skipped" if entry.event == SKIPPED else ""
    return (
        f"`{number:>2}` {truncate(entry.track.title, 55)}"
        f" · {duration(entry.track.length_ms)} · <t:{stamp}:R>{ending}"
    )


def playlist_option(playlist: PlaylistSummary) -> str:
    """How big a saved playlist is, and whether it is the viewer's own."""
    tracks = f"{playlist.track_count} track{'' if playlist.track_count == 1 else 's'}"
    return f"{tracks} · {'shared' if playlist.is_public else 'yours'}"


def playlist_heading(count: int) -> str:
    return (
        "### Your playlists\n"
        f"-# {count} available. Loading one adds every track to the queue."
    )


def playlist_queued(name: str, tracks: list[Track]) -> str:
    """Confirm a load by naming a few tracks and counting the rest."""
    listing = "\n".join(
        f"-# {truncate(track.title, 60)}" for track in tracks[:UPCOMING_SHOWN]
    )
    remaining = len(tracks) - UPCOMING_SHOWN
    if remaining > 0:
        listing += f"\n-# and {remaining} more"
    return f"Queued **{len(tracks)}** tracks from **{truncate(name)}**.\n{listing}"


def _source_line(track: Track) -> str:
    """Where it was asked for, and where it actually came from if that differs."""
    played = track.played_source or track.source
    if played == track.requested_source:
        return played
    return f"{track.requested_source} → {played}"
