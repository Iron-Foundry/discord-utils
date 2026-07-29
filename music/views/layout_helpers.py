"""Shared Components V2 layout utilities for the music views.

Same shape as `discord-server/features/tickets/views/_layout_helpers.py`, which
is the established pattern in this monorepo. discord-utils had no LayoutView
before this.
"""

from __future__ import annotations

import discord


def status_layout(content: str) -> discord.ui.LayoutView:
    """Minimal ephemeral status/error message as a LayoutView."""
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(discord.ui.Container(discord.ui.TextDisplay(content)))
    return view


async def reply(interaction: discord.Interaction, content: str) -> None:
    """Answer an interaction with an ephemeral status message."""
    await interaction.response.send_message(view=status_layout(content), ephemeral=True)


async def follow_up(interaction: discord.Interaction, content: str) -> None:
    """Say something after the interaction has already been deferred."""
    await interaction.followup.send(view=status_layout(content), ephemeral=True)
