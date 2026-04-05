from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from loguru import logger

from command_infra.checks import handle_check_failure, is_staff

if TYPE_CHECKING:
    from chat_events.service import ChatEventsService


class ChatEventsGroup(
    app_commands.Group, name="chatevents", description="Clan event channel config"
):
    """Slash command group for configuring the clan events relay channel."""

    def __init__(self, service: ChatEventsService) -> None:
        super().__init__()
        self._service = service

    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await handle_check_failure(interaction, error)

    # ------------------------------------------------------------------
    # /chatevents setchannel <channel>
    # ------------------------------------------------------------------

    @app_commands.command(
        name="setchannel",
        description="Set the channel for all clan events and chat relay",
    )
    @app_commands.describe(channel="The text channel to post clan events and chat in")
    @is_staff()
    async def setchannel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        logger.debug(
            f"ChatEvents: setchannel invoked by {interaction.user}, "
            f"channel={channel.name!r}"
        )
        await self._service.set_channel(channel.id)
        await interaction.response.send_message(
            f"Clan events and chat relay will be posted in {channel.mention}.",
            ephemeral=True,
        )

    # ------------------------------------------------------------------
    # /chatevents status
    # ------------------------------------------------------------------

    @app_commands.command(
        name="status", description="Show the configured clan events channel"
    )
    @is_staff()
    async def status(self, interaction: discord.Interaction) -> None:
        logger.debug(f"ChatEvents: status invoked by {interaction.user}")
        channel_id = self._service.channel_id
        if channel_id:
            await interaction.response.send_message(
                f"Clan events channel: <#{channel_id}>", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "No clan events channel configured. Use `/chatevents setchannel` to set one.",
                ephemeral=True,
            )
