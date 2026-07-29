"""Executing web commands against the sessions this process owns.

api-backend never holds a Lavalink player and this process never holds a web
request, so the only thing crossing between them is an intent on
`music:commands`. Authority is re-checked here rather than trusted from the
publisher: the "you must be in the channel" rule has to hold whichever surface
the command came from. State travels the other way; see `music/notify.py`.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Protocol

from loguru import logger
from valkey.asyncio import Valkey

from music import keys
from music.dispatch import CommandError, MusicCommand, apply
from music.playlists import PlaylistClient
from music.session import MusicSession

RECONNECT_SECONDS = 5


class SessionSource(Protocol):
    """What the bridge needs from the music service, and nothing more."""

    @property
    def playlists(self) -> PlaylistClient | None: ...

    def session(self, voice_channel_id: int) -> MusicSession | None: ...

    async def may_control(self, voice_channel_id: int, user_id: int) -> bool: ...


class CommandBridge:
    """Subscribes to `music:commands` and runs what it is allowed to run."""

    def __init__(self, valkey_uri: str, service: SessionSource) -> None:
        self._valkey_uri = valkey_uri
        self._service = service
        self._task: asyncio.Task[None] | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="music-command-bridge")
        logger.info("Music: command bridge listening on {}", keys.COMMANDS)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def handle(self, raw: str | bytes) -> None:
        """Authorise one command and run it. Never raises at the caller."""
        try:
            command = MusicCommand.model_validate_json(raw)
        except ValueError as exc:
            logger.warning("Music: unreadable command {!r}: {}", raw, exc)
            return

        session = self._service.session(command.voice_channel_id)
        if session is None:
            # Another process owns it, or it ended between publish and delivery.
            return
        if not await self._service.may_control(
            command.voice_channel_id, command.actor_id
        ):
            logger.info(
                "Music: refused {} from {} - not in channel {}",
                command.action,
                command.actor_id,
                command.voice_channel_id,
            )
            return

        try:
            await apply(command, session, self._service.playlists)
        except CommandError as exc:
            logger.warning("Music: command {} refused: {}", command.action, exc)
        except Exception as exc:
            logger.warning("Music: command {} failed: {}", command.action, exc)

    async def _run(self) -> None:
        while True:
            sub = Valkey.from_url(self._valkey_uri, socket_timeout=None)
            try:
                async with sub.pubsub() as ps:
                    await ps.subscribe(keys.COMMANDS)
                    async for message in ps.listen():
                        if message["type"] == "message":
                            await self.handle(message["data"])
            except asyncio.CancelledError:
                await sub.aclose()
                return
            except Exception as exc:
                logger.warning(
                    "Music: command bridge lost its connection ({}), retrying in {}s",
                    exc,
                    RECONNECT_SECONDS,
                )
                await sub.aclose()
                await asyncio.sleep(RECONNECT_SECONDS)
