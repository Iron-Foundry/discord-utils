"""Turning a web command into a call on a live session.

The web surface never touches Lavalink. It publishes an intent, and this is the
one place that intent becomes a real transport call, so a control added to the
website cannot do anything a panel button could not already do.
"""

from __future__ import annotations

from pydantic import BaseModel

from music.models import LoopMode
from music.playlists import (
    PlaylistClient,
    PlaylistError,
    SavedTrack,
    to_track,
    to_tracks,
)
from music.queue import QueueFullError
from music.session import MusicSession


class MusicCommand(BaseModel):
    """One instruction from the web, as it travels over `music:commands`."""

    voice_channel_id: int
    actor_id: int
    action: str
    paused: bool | None = None
    shuffle: bool | None = None
    index: int | None = None
    destination: int | None = None
    position_ms: int | None = None
    volume: int | None = None
    loop: LoopMode | None = None
    playlist_id: int | None = None
    tracks: list[SavedTrack] | None = None


class CommandError(RuntimeError):
    """The command named something the session cannot do."""


async def apply(
    command: MusicCommand,
    session: MusicSession,
    playlists: PlaylistClient | None = None,
) -> None:
    """Run one command against a session that has already been authorised."""
    actor = command.actor_id
    match command.action:
        case "pause":
            await session.pause(actor, bool(command.paused))
        case "skip":
            await session.skip(actor)
        case "stop":
            await session.stop(actor)
        case "shuffle":
            if command.shuffle is None:
                raise CommandError("shuffle is required")
            await session.set_shuffle(actor, command.shuffle)
        case "seek":
            await session.seek(actor, _required(command.position_ms, "position_ms"))
        case "volume":
            await session.set_volume(actor, _required(command.volume, "volume"))
        case "loop":
            if command.loop is None:
                raise CommandError("loop is required")
            await session.set_loop(actor, command.loop)
        case "remove":
            await session.remove(actor, _required(command.index, "index"))
        case "jump":
            await session.jump(actor, _required(command.index, "index"))
        case "move":
            await session.move(
                actor,
                _required(command.index, "index"),
                _required(command.destination, "destination"),
            )
        case "add":
            await _add(command, session)
        case "load_playlist":
            await _load_playlist(command, session, playlists)
        case unknown:
            raise CommandError(f"Unknown music command {unknown!r}")


async def _add(command: MusicCommand, session: MusicSession) -> None:
    """Queue tracks the website already resolved.

    The metadata travels on the command rather than being searched again here:
    the caller picked a specific result, and re-running the query could queue a
    different one. Audio is looked up when the track reaches the front of the
    queue, exactly as a saved playlist row is.
    """
    if not command.tracks:
        raise CommandError("tracks is required")
    tracks = [to_track(row, requester_id=command.actor_id) for row in command.tracks]
    label = tracks[0].title if len(tracks) == 1 else f"{len(tracks)} tracks"
    try:
        await session.enqueue(tracks, actor_id=command.actor_id, label=label)
    except QueueFullError as exc:
        raise CommandError(str(exc)) from exc


async def _load_playlist(
    command: MusicCommand,
    session: MusicSession,
    playlists: PlaylistClient | None,
) -> None:
    """Queue a saved playlist, exactly as the panel's own control does."""
    if playlists is None:
        raise CommandError("Playlists are not configured")
    playlist_id = _required(command.playlist_id, "playlist_id")
    try:
        playlist = await playlists.detail(command.actor_id, playlist_id)
    except PlaylistError as exc:
        raise CommandError(str(exc)) from exc

    tracks = to_tracks(playlist, requester_id=command.actor_id)
    if not tracks:
        raise CommandError("That playlist has no tracks in it")
    try:
        await session.enqueue(tracks, actor_id=command.actor_id, label=playlist.name)
    except QueueFullError as exc:
        raise CommandError(str(exc)) from exc


def _required(value: int | None, name: str) -> int:
    if value is None:
        raise CommandError(f"{name} is required")
    return value
