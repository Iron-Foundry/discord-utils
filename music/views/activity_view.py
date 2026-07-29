"""The ephemeral activity feed.

Read-only, so it needs no in-channel check: it shows what already happened in a
channel the viewer can see. Entries are rendered with Discord relative
timestamps, so the client ages them without the view being edited.
"""

from __future__ import annotations

import discord

from music.views.context import PanelContext
from music.views.layout_helpers import status_layout

SHOWN = 15


async def send_activity(
    interaction: discord.Interaction, context: PanelContext
) -> None:
    """Show the recent interactions with this session."""
    entries = await context.session.activity.recent(SHOWN)
    if not entries:
        await interaction.response.send_message(
            view=status_layout("Nothing has happened yet."), ephemeral=True
        )
        return

    body = "\n".join(entry.render() for entry in entries)
    await interaction.response.send_message(
        view=status_layout(f"### Recent activity\n{body}"), ephemeral=True
    )
