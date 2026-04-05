from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from loguru import logger

from command_infra.checks import handle_check_failure, is_senior_staff
from command_infra.help_registry import HelpEntry, HelpGroup, HelpRegistry

if TYPE_CHECKING:
    from temp_vc.service import TempVCService


def register_help(registry: HelpRegistry) -> None:
    """Register help entries for the tempvc command group."""
    registry.add_group(
        HelpGroup(
            name="tempvc",
            description="Manage temporary voice channels",
            commands=[
                HelpEntry(
                    "/tempvc setup <category>",
                    "Create the trigger voice channel in a category",
                    "Senior Staff",
                ),
                HelpEntry(
                    "/tempvc whitelist add <member>",
                    "Add a member to your temp VC whitelist",
                    "Member",
                ),
                HelpEntry(
                    "/tempvc whitelist remove <member>",
                    "Remove a member from your temp VC whitelist",
                    "Member",
                ),
                HelpEntry(
                    "/tempvc whitelist list",
                    "Show your temp VC whitelist",
                    "Member",
                ),
            ],
        )
    )


# ---------------------------------------------------------------------------
# Whitelist subgroup
# ---------------------------------------------------------------------------


class WhitelistGroup(
    app_commands.Group, name="whitelist", description="Manage your temp VC whitelist"
):
    """Subgroup for managing the per-user whitelist for private temp VCs."""

    def __init__(self, service: TempVCService) -> None:
        super().__init__()
        self._service = service

    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await handle_check_failure(interaction, error)

    # ------------------------------------------------------------------
    # /tempvc whitelist add <member>
    # ------------------------------------------------------------------

    @app_commands.command(name="add", description="Add a member to your whitelist")
    @app_commands.describe(member="The member to allow into your private temp VC")
    async def add(
        self, interaction: discord.Interaction, member: discord.Member
    ) -> None:
        logger.debug(
            f"TempVC: whitelist add invoked by {interaction.user},"
            f" target={member.display_name!r}"
        )
        if member.id == interaction.user.id:
            await interaction.response.send_message(
                "❌ You can't whitelist yourself.", ephemeral=True
            )
            return
        added = await self._service.add_to_whitelist(interaction.user.id, member.id)
        if added:
            await interaction.response.send_message(
                f"✅ {member.mention} added to your whitelist.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"{member.mention} is already on your whitelist.", ephemeral=True
            )

    # ------------------------------------------------------------------
    # /tempvc whitelist remove <member>
    # ------------------------------------------------------------------

    @app_commands.command(
        name="remove", description="Remove a member from your whitelist"
    )
    @app_commands.describe(member="The member to remove from your whitelist")
    async def remove(
        self, interaction: discord.Interaction, member: discord.Member
    ) -> None:
        logger.debug(
            f"TempVC: whitelist remove invoked by {interaction.user},"
            f" target={member.display_name!r}"
        )
        removed = await self._service.remove_from_whitelist(
            interaction.user.id, member.id
        )
        if removed:
            await interaction.response.send_message(
                f"⛔ {member.mention} removed from your whitelist.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"{member.mention} was not on your whitelist.", ephemeral=True
            )

    # ------------------------------------------------------------------
    # /tempvc whitelist list
    # ------------------------------------------------------------------

    @app_commands.command(name="list", description="Show your temp VC whitelist")
    async def list_whitelist(self, interaction: discord.Interaction) -> None:
        logger.debug(f"TempVC: whitelist list invoked by {interaction.user}")
        whitelist = await self._service.get_whitelist(interaction.user.id)
        embed = discord.Embed(
            title="Your Temp VC Whitelist", color=discord.Color.blurple()
        )
        if not whitelist:
            embed.description = "Your whitelist is empty."
        else:
            embed.description = "\n".join(f"<@{uid}>" for uid in whitelist)
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ---------------------------------------------------------------------------
# Main tempvc group
# ---------------------------------------------------------------------------


class TempVCGroup(app_commands.Group, name="tempvc", description="Temp VC management"):
    """Slash command group for managing the temp VC feature."""

    def __init__(self, service: TempVCService) -> None:
        super().__init__()
        self._service = service
        self.add_command(WhitelistGroup(service=service))

    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await handle_check_failure(interaction, error)

    # ------------------------------------------------------------------
    # /tempvc setup <category>
    # ------------------------------------------------------------------

    @app_commands.command(
        name="setup",
        description="Create the trigger voice channel in a category",
    )
    @app_commands.describe(
        category="The category where the trigger channel will be created"
    )
    @is_senior_staff()
    async def setup(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
    ) -> None:
        logger.debug(
            f"TempVC: setup invoked by {interaction.user}, category={category.name!r}"
        )
        await interaction.response.defer(ephemeral=True, thinking=True)
        channel = await self._service.create_trigger_channel(category)
        await interaction.followup.send(
            f"✅ Trigger channel {channel.mention} created in **{category.name}**.\n"
            "Members who join it will get a private voice channel automatically.",
            ephemeral=True,
        )
