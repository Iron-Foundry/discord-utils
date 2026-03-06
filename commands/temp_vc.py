from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from loguru import logger

from commands.checks import handle_check_failure, is_senior_staff, is_staff
from commands.help_registry import HelpEntry, HelpGroup, HelpRegistry

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
                    "/tempvc gim add <role>",
                    "Add a role as a GIM group (members share a temp VC)",
                    "Senior Staff",
                ),
                HelpEntry(
                    "/tempvc gim remove <role>",
                    "Remove a role from GIM groups",
                    "Senior Staff",
                ),
                HelpEntry(
                    "/tempvc gim list",
                    "List all configured GIM group roles",
                    "Staff",
                ),
            ],
        )
    )


# ---------------------------------------------------------------------------
# GIM subgroup
# ---------------------------------------------------------------------------


class GIMGroup(app_commands.Group, name="gim", description="Manage GIM group roles"):
    """Subgroup for configuring which roles count as GIM groups."""

    def __init__(self, service: TempVCService) -> None:
        super().__init__()
        self._service = service

    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await handle_check_failure(interaction, error)

    # ------------------------------------------------------------------
    # /tempvc gim add <role>
    # ------------------------------------------------------------------

    @app_commands.command(name="add", description="Add a role as a GIM group")
    @app_commands.describe(role="The role to add as a GIM group")
    @is_senior_staff()
    async def add(self, interaction: discord.Interaction, role: discord.Role) -> None:
        logger.debug(
            f"TempVC: gim add invoked by {interaction.user}, role={role.name!r}"
        )
        added = await self._service.add_gim_role(role.id)
        if added:
            await interaction.response.send_message(
                f"✅ {role.mention} added as a GIM group.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"{role.mention} is already a GIM group.", ephemeral=True
            )

    # ------------------------------------------------------------------
    # /tempvc gim remove <role>
    # ------------------------------------------------------------------

    @app_commands.command(name="remove", description="Remove a role from GIM groups")
    @app_commands.describe(role="The role to remove")
    @is_senior_staff()
    async def remove(
        self, interaction: discord.Interaction, role: discord.Role
    ) -> None:
        logger.debug(
            f"TempVC: gim remove invoked by {interaction.user}, role={role.name!r}"
        )
        removed = await self._service.remove_gim_role(role.id)
        if removed:
            await interaction.response.send_message(
                f"⛔ {role.mention} removed from GIM groups.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"{role.mention} was not a GIM group.", ephemeral=True
            )

    # ------------------------------------------------------------------
    # /tempvc gim list
    # ------------------------------------------------------------------

    @app_commands.command(name="list", description="List all GIM group roles")
    @is_staff()
    async def list_gim(self, interaction: discord.Interaction) -> None:
        logger.debug(f"TempVC: gim list invoked by {interaction.user}")
        role_ids = self._service.gim_role_ids
        embed = discord.Embed(title="GIM Group Roles", color=discord.Color.blurple())
        if not role_ids:
            embed.description = "No GIM group roles configured."
        else:
            embed.description = "\n".join(f"<@&{rid}>" for rid in role_ids)
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ---------------------------------------------------------------------------
# Main tempvc group
# ---------------------------------------------------------------------------


class TempVCGroup(app_commands.Group, name="tempvc", description="Temp VC management"):
    """Slash command group for managing the temp VC feature."""

    def __init__(self, service: TempVCService) -> None:
        super().__init__()
        self._service = service
        self.add_command(GIMGroup(service=service))

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
