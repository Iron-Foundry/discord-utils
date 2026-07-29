"""What every panel control needs, and the check every one of them runs first."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import discord

from music.playlists import PlaylistClient
from music.session import MusicSession
from music.views.layout_helpers import reply

Guard = Callable[[int], Awaitable[bool]]

DENIED = "Join the voice channel to control the music."


@dataclass(slots=True)
class PanelContext:
    """The session a control acts on, and who is allowed to act on it."""

    session: MusicSession
    guard: Guard
    playlists: PlaylistClient | None = None

    async def allows(self, interaction: discord.Interaction) -> bool:
        """Authorise an interaction, answering it directly when it is refused.

        Control authority is "anyone connected to the channel", and it is read
        from the same Valkey roster the web surface reads, so the two surfaces
        cannot drift apart.
        """
        if await self.guard(interaction.user.id):
            return True
        await reply(interaction, DENIED)
        return False
