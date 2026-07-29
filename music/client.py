"""The thin player bot client.

Player bots hold no command tree and no services. They exist to occupy a voice
channel and stream audio, so they run the narrowest intents that still allow a
voice connection: guilds plus voice states, neither of which is privileged.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import discord
from loguru import logger

LOGIN_TIMEOUT_SECONDS = 30.0

EventHandler = Callable[[Any], Awaitable[None]]


def player_intents() -> discord.Intents:
    """Guilds plus voice states, which discord.py documents as required for voice."""
    intents = discord.Intents.none()
    intents.guilds = True
    intents.voice_states = True
    return intents


class PlayerClient(discord.Client):
    """A single music player bot and the task running its gateway session."""

    def __init__(self, bot_index: int) -> None:
        super().__init__(intents=player_intents())
        self.bot_index = bot_index
        self.login_task: asyncio.Task[None] | None = None
        # wavelink dispatches its events onto the client that owns the node, so
        # these are how the session manager hears about this bot's playback.
        self.track_end_handler: EventHandler | None = None
        self.inactive_handler: EventHandler | None = None

    async def on_ready(self) -> None:
        logger.info("MusicPool: bot {} logged in as {}", self.bot_index, self.user)

    async def on_wavelink_track_end(self, payload: Any) -> None:
        if self.track_end_handler is not None:
            await self.track_end_handler(payload)

    async def on_wavelink_inactive_player(self, player: Any) -> None:
        if self.inactive_handler is not None:
            await self.inactive_handler(player)

    async def launch(self, token: str) -> None:
        """Log in and wait until the gateway session is usable.

        Tears the client down on failure so a rejected token or a slow gateway
        never leaves a half-open session behind for the pool to lease again.
        Callers needing a different budget wrap this in ``asyncio.timeout``.
        """
        self.login_task = asyncio.create_task(
            self.start(token), name=f"music-bot-{self.bot_index}"
        )
        ready = asyncio.create_task(self.wait_until_ready())
        done, _ = await asyncio.wait(
            {ready, self.login_task},
            timeout=LOGIN_TIMEOUT_SECONDS,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if ready in done:
            return

        ready.cancel()
        # start() finishing before ready means the login itself failed. result()
        # re-raises whatever it hit, so the caller sees the real cause.
        if self.login_task in done:
            try:
                self.login_task.result()
            except Exception as exc:
                await self.shutdown()
                raise RuntimeError(
                    f"music bot {self.bot_index} failed to log in"
                ) from exc

        await self.shutdown()
        raise TimeoutError(
            f"music bot {self.bot_index} was not ready in {LOGIN_TIMEOUT_SECONDS}s"
        )

    async def shutdown(self) -> None:
        """Close the gateway session and wait for its task to finish."""
        if not self.is_closed():
            await self.close()
        if self.login_task is not None:
            self.login_task.cancel()
            await asyncio.gather(self.login_task, return_exceptions=True)
            self.login_task = None
