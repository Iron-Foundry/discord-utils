"""Opens and closes playback sessions, one per voice channel.

This is where the client-layer rules that keep five bots from stepping on each
other are actually applied: the channel is re-resolved from the player bot's own
cache before connecting, and the player is constructed against that bot's node
rather than whichever node the Pool would have picked.
"""

from __future__ import annotations

import discord
import wavelink
from loguru import logger
from valkey.asyncio import Valkey

from music.connect import own_channel, rename
from music.naming import guild_lookup
from music.node_cache import NodeCache
from music.nodes import IDLE_TIMEOUT_SECONDS, player_class
from music.notify import publish_closed, publish_state, with_state_publish
from music.panel import PanelController, attach_panel
from music.playlists import PlaylistClient
from music.pool import BotPool
from music.session import MusicSession
from music.stats import SESSION_ENDED, SESSION_STARTED, StatsStream
from music.voice import VoiceRoster, human_ids


class SessionManager:
    """Owns the live sessions and the nodes behind them."""

    def __init__(
        self,
        pool: BotPool,
        valkey: Valkey,
        guild: discord.Guild,
        lavalink_uri: str,
        lavalink_password: str,
        playlists: PlaylistClient | None = None,
    ) -> None:
        self._pool = pool
        self._valkey = valkey
        self._guild = guild
        self._playlists = playlists
        self._nodes = NodeCache(lavalink_uri, lavalink_password)
        self._sessions: dict[int, MusicSession] = {}
        self._panels: dict[int, PanelController] = {}

    def get(self, voice_channel_id: int) -> MusicSession | None:
        return self._sessions.get(voice_channel_id)

    @property
    def active(self) -> list[MusicSession]:
        return list(self._sessions.values())

    async def open(self, channel: discord.VoiceChannel) -> MusicSession:
        """Lease a bot for this channel, connect it, and start its session."""
        existing = self._sessions.get(channel.id)
        if existing is not None:
            return existing

        lease = await self._pool.acquire(channel.id)
        client = self._pool.client_for(lease.bot_index)
        if client is None:
            raise RuntimeError(f"Music bot {lease.bot_index} has no live client")

        try:
            player_channel = own_channel(client, channel.id, lease.bot_index)
        except RuntimeError:
            await self._pool.release(channel.id)
            raise

        node = await self._nodes.get(lease.bot_index, client)
        await rename(player_channel.guild, lease.nickname)
        player = await player_channel.connect(
            cls=player_class(node), self_deaf=True, reconnect=True
        )
        # Nothing starts wavelink's idle timer on connect: it runs from a track
        # end, or from this setter, which starts it when the player is connected
        # and not playing (`player.py:621-622`). A session that connects and
        # never plays - an abandoned search, a query that found nothing - would
        # otherwise hold its bot for as long as the process lives.
        player.inactive_timeout = IDLE_TIMEOUT_SECONDS

        # The main bot's guild, which holds a member cache. A player bot's would
        # not: they run without the members intent.
        names = guild_lookup(self._guild)
        session = MusicSession(self._valkey, player, channel.id, self._guild.id, names)
        self._sessions[channel.id] = session
        client.track_end_handler = self._on_track_end
        client.inactive_handler = self._on_inactive
        # The roster is synced before the panel exists, because the panel's own
        # controls read it to decide who may press them.
        await VoiceRoster(self._valkey, channel.id).sync(human_ids(channel))
        panel = await attach_panel(channel, session, self._valkey, self._playlists)
        self._panels[channel.id] = panel
        # The panel and the web surface both redraw on the same signal, so the
        # notice is chained onto the panel refresh rather than given its own hook.
        session.on_change = with_state_publish(session, self._valkey, panel.refresh)
        await session.state.set_channel(guild_id=self._guild.id, name=channel.name)
        await session.state.initialise()
        await publish_state(self._valkey, session)
        await StatsStream(self._valkey, self._guild.id).session_event(
            SESSION_STARTED, channel.id
        )
        return session

    async def close(self, voice_channel_id: int) -> None:
        """End a session and hand its bot back to the pool."""
        session = self._sessions.pop(voice_channel_id, None)
        panel = self._panels.pop(voice_channel_id, None)
        lease = await self._pool.existing(voice_channel_id)

        if panel is not None:
            await panel.close()
        if session is not None:
            await StatsStream(self._valkey, self._guild.id).session_event(
                SESSION_ENDED, voice_channel_id
            )
            await session.player.disconnect()

        if lease is not None:
            await self._nodes.drop(lease.bot_index)
        await self._pool.release(voice_channel_id)
        await publish_closed(self._valkey, voice_channel_id)
        logger.info("Music: session closed for channel {}", voice_channel_id)

    async def close_all(self) -> None:
        for voice_channel_id in list(self._sessions):
            await self.close(voice_channel_id)

    async def _on_track_end(self, payload: wavelink.TrackEndEventPayload) -> None:
        session = self._session_for(payload.player)
        if session is not None:
            await session.advance(payload.reason)

    async def _on_inactive(self, player: wavelink.Player) -> None:
        session = self._session_for(player)
        if session is not None:
            logger.info("Music: channel {} went idle", session.voice_channel_id)
            await self.close(session.voice_channel_id)

    def _session_for(self, player: wavelink.Player | None) -> MusicSession | None:
        if player is None:
            return None
        return self._sessions.get(player.channel.id)
