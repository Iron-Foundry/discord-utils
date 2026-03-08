from __future__ import annotations

from typing import Any

import discord
from discord import app_commands

from command_infra.help_registry import HelpEntry, HelpGroup, HelpRegistry

_ACCESS_BADGES = {
    "Everyone": "🟢 Everyone",
    "Staff": "🔵 Staff",
    "Senior Staff": "🟡 Senior Staff",
}


def _groups_embed(groups: list[HelpGroup]) -> discord.Embed:
    embed = discord.Embed(
        title="The Foundry — Available Commands",
        description="Use `/help <group>` to see commands in a specific group.",
        color=discord.Color.blurple(),
    )
    for group in groups:
        embed.add_field(name=f"`{group.name}`", value=group.description, inline=False)
    return embed


def _group_embed(group: HelpGroup) -> discord.Embed:
    embed = discord.Embed(
        title=f"Commands — {group.name}",
        description=group.description,
        color=discord.Color.blurple(),
    )
    for cmd in group.commands:
        badge = _ACCESS_BADGES.get(cmd.access, cmd.access)
        embed.add_field(
            name=cmd.name,
            value=f"{cmd.description}\n{badge}",
            inline=False,
        )
    return embed


def make_help_command(registry: HelpRegistry) -> app_commands.Command[Any, Any, Any]:
    """Return a ready-to-add /help slash command backed by registry."""

    @app_commands.command(name="help", description="Show available commands")
    @app_commands.describe(group="Filter by command group")
    async def help_cmd(
        interaction: discord.Interaction, group: str | None = None
    ) -> None:
        if group is None:
            await interaction.response.send_message(
                embed=_groups_embed(registry.groups()), ephemeral=True
            )
            return

        found = registry.get_group(group)
        if found is None:
            await interaction.response.send_message(
                f"Unknown group `{group}`. Use `/help` to see all groups.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=_group_embed(found), ephemeral=True
        )

    @help_cmd.autocomplete("group")
    async def group_autocomplete(
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name=g.name, value=g.name)
            for g in registry.groups()
            if current.lower() in g.name.lower()
        ]

    return help_cmd  # type: ignore[return-value]


def register_help(registry: HelpRegistry) -> None:
    """Register the /help command's own help entry."""
    registry.add_group(
        HelpGroup(
            name="help",
            description="Command help and documentation",
            commands=[
                HelpEntry(
                    name="/help",
                    description="Show all available command groups",
                    access="Everyone",
                ),
                HelpEntry(
                    name="/help <group>",
                    description="Show commands in a specific group",
                    access="Everyone",
                ),
            ],
        )
    )
