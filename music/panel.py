"""Posts and maintains the panel message for one session.

The panel lives in the voice channel's own integrated text chat, so no other
channel is touched and, for a temp VC, the panel is deleted along with the
channel it belongs to.

It is posted by the orchestrator rather than the player bot: the orchestrator
already has text permissions everywhere, which is why the player bots only ever
needed View Channel, Connect, Speak and Move Members.
"""

from __future__ import annotations

import contextlib

import discord
from loguru import logger
from valkey.asyncio import Valkey

from music.playlists import PlaylistClient
from music.session import MusicSession
from music.views.context import PanelContext
from music.views.panel_view import MusicPanel
from music.views.snapshot import take_snapshot
from music.voice import VoiceRoster

SWEEP_LIMIT = 20


async def attach_panel(
    channel: discord.VoiceChannel,
    session: MusicSession,
    valkey: Valkey,
    playlists: PlaylistClient | None = None,
) -> PanelController:
    """Post a panel for this session and keep it in step with the session."""
    roster = VoiceRoster(valkey, session.voice_channel_id)
    context = PanelContext(
        session=session, guard=roster.may_control, playlists=playlists
    )
    panel = PanelController(channel, session, context)
    session.on_change = panel.refresh
    await panel.post()
    return panel


class PanelController:
    """Owns the one panel message belonging to a session."""

    def __init__(
        self,
        channel: discord.VoiceChannel,
        session: MusicSession,
        context: PanelContext,
    ) -> None:
        self._channel = channel
        self._session = session
        self._context = context
        self._message: discord.Message | None = None

    async def post(self) -> None:
        """Sweep any panel a previous process left, then post a fresh one."""
        await self._sweep()
        try:
            self._message = await self._channel.send(view=await self._build())
        except discord.HTTPException as exc:
            logger.warning("Music: could not post the panel: {}", exc)

    async def refresh(self) -> None:
        """Redraw after a state change. Never called on a timer."""
        if self._message is None:
            return
        try:
            await self._message.edit(view=await self._build())
        except discord.NotFound:
            # Someone deleted it. Post a new one rather than going silent.
            self._message = None
            await self.post()
        except discord.HTTPException as exc:
            logger.warning("Music: could not refresh the panel: {}", exc)

    async def close(self) -> None:
        """Remove the panel when its session ends."""
        if self._message is None:
            return
        message, self._message = self._message, None
        # A deleted channel takes its messages with it, so a failure here is
        # the expected case for a temp VC, not an error.
        with contextlib.suppress(discord.HTTPException):
            await message.delete()

    async def _build(self) -> MusicPanel:
        return MusicPanel(self._context, await take_snapshot(self._session))

    async def _sweep(self) -> None:
        """Delete panels this bot left in this channel before now.

        Sessions never survive a restart, so any panel still here is orphaned:
        its buttons point at a session that no longer exists. Message ids are
        not persisted anywhere, so the channel's own history is the only record
        of them.
        """
        me = self._channel.guild.me
        try:
            async for message in self._channel.history(limit=SWEEP_LIMIT):
                if message.author.id == me.id and message.flags.components_v2:
                    await message.delete()
        except discord.HTTPException as exc:
            logger.warning("Music: could not sweep old panels: {}", exc)
