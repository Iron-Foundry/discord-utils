"""Music service: owns the bot pool and routes channels to their player bot."""

from __future__ import annotations

import discord
from loguru import logger
from valkey.asyncio import Valkey

from core.service_base import Service
from music.bridge import CommandBridge
from music.manager import SessionManager
from music.names import combinations
from music.notify import StateKeepalive
from music.playlists import PlaylistClient
from music.pool import MAX_BOTS, BotPool
from music.session import MusicSession
from music.voice import VoiceRoster


def parse_tokens(raw: str | None) -> list[str]:
    """Split MUSIC_BOT_TOKENS. The token count is the pool size."""
    tokens = [token.strip() for token in (raw or "").split(",") if token.strip()]
    if len(tokens) > MAX_BOTS:
        logger.warning(
            "MusicService: {} tokens configured, using the first {}",
            len(tokens),
            MAX_BOTS,
        )
    return tokens[:MAX_BOTS]


def build_playlist_client(api_url: str, service_key: str) -> PlaylistClient | None:
    """The playlist reader, or None when either half of its config is missing.

    None rather than a client that always fails: the panel and `/playlist` both
    check for it, so an unconfigured deployment simply has no playlist control
    instead of a button that errors when pressed.
    """
    if not api_url or not service_key:
        logger.info(
            "Music: playlists disabled - API_BACKEND_URL or METRICS_API_KEY is not set"
        )
        return None
    return PlaylistClient(api_url, service_key)


class MusicService(Service):
    """Leases player bots to voice channels on demand."""

    def __init__(
        self,
        guild: discord.Guild,
        valkey: Valkey,
        tokens: list[str],
        lavalink_uri: str,
        lavalink_password: str,
        api_url: str = "",
        service_key: str = "",
        valkey_uri: str = "",
    ) -> None:
        self._guild = guild
        self._valkey = valkey
        self._pool = BotPool(tokens, valkey)
        self._playlists = build_playlist_client(api_url, service_key)
        self._manager = SessionManager(
            self._pool,
            valkey,
            guild,
            lavalink_uri,
            lavalink_password,
            self._playlists,
        )
        # No URI means no second connection to open, so the website simply has
        # no control over playback - exactly as an unconfigured API means no
        # playlists. Discord is unaffected either way.
        self._bridge = CommandBridge(valkey_uri, self) if valkey_uri else None
        self._keepalive = StateKeepalive(valkey, lambda: self.sessions)

    @property
    def pool(self) -> BotPool:
        return self._pool

    @property
    def playlists(self) -> PlaylistClient | None:
        """The saved-playlist reader, or None when the API is not configured."""
        return self._playlists

    @property
    def valkey(self) -> Valkey:
        return self._valkey

    @property
    def sessions(self) -> list[MusicSession]:
        return self._manager.active

    def session(self, voice_channel_id: int) -> MusicSession | None:
        """The live session for a channel, if there is one."""
        return self._manager.get(voice_channel_id)

    async def initialize(self) -> None:
        """Clear state left by a previous process, since sessions never survive one."""
        await self._pool.reset_state()
        logger.info(
            "MusicService: initialized with {} bot(s), {} possible nicknames",
            self._pool.size,
            combinations(),
        )

    async def post_ready(self) -> None:
        await self._pool.start_heartbeat()
        await self._keepalive.start()
        if self._bridge is not None:
            await self._bridge.start()

    async def join(self, channel: discord.VoiceChannel) -> MusicSession:
        """Lease a bot for this channel, connect it, and open its session."""
        return await self._manager.open(channel)

    async def leave(self, voice_channel_id: int) -> None:
        """End the session in this channel and free its bot."""
        await self._manager.close(voice_channel_id)

    async def may_control(self, voice_channel_id: int, user_id: int) -> bool:
        """Anyone connected to the channel controls it, on either surface."""
        return await VoiceRoster(self._valkey, voice_channel_id).may_control(user_id)

    async def shutdown(self) -> None:
        await self._keepalive.stop()
        if self._bridge is not None:
            await self._bridge.stop()
        await self._manager.close_all()
        await self._pool.shutdown()
