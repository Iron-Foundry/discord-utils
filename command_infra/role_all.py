"""Role-all command — assign a role to all (or filtered) guild members."""

from __future__ import annotations

import math

import discord
from discord import app_commands
from loguru import logger

from command_infra.checks import handle_check_failure, is_staff
from command_infra.help_registry import HelpEntry, HelpGroup, HelpRegistry
from core.throttle import Throttle

_ROLE_ASSIGN_RATE = 1.0  # role assignments per second


def _format_duration(seconds: int) -> str:
    """Format a duration in seconds as a human-readable string."""
    if seconds < 60:
        return f"{seconds}s"
    minutes, secs = divmod(seconds, 60)
    return f"{minutes}m {secs}s" if secs else f"{minutes}m"


def _collect_targets(
    guild: discord.Guild,
    role: discord.Role,
    filter_role: discord.Role | None,
) -> tuple[list[discord.Member], int]:
    """Return (targets, already_have_count) for the role assignment.

    Targets are non-bot members who don't yet have the role.
    If filter_role is given, only members with that role are considered.
    already_have_count is how many eligible members already hold the role.
    """
    pool = [m for m in guild.members if not m.bot]
    if filter_role is not None:
        pool = [m for m in pool if filter_role in m.roles]

    targets = [m for m in pool if role not in m.roles]
    already_have = len(pool) - len(targets)
    return targets, already_have


async def _assign_role_to_all(
    targets: list[discord.Member],
    role: discord.Role,
) -> tuple[int, int]:
    """Assign role to each target member via a throttled queue.

    Returns (succeeded, failed) counts.
    """
    succeeded = 0
    failed = 0

    async def assign(member: discord.Member) -> None:
        nonlocal succeeded, failed
        try:
            await member.add_roles(role, reason="/roleall command")
            succeeded += 1
        except discord.HTTPException as e:
            logger.warning(f"roleall: failed to assign {role.name} to {member}: {e}")
            failed += 1

    throttle: Throttle[discord.Member] = Throttle(worker=assign, rate=_ROLE_ASSIGN_RATE)
    throttle.start()
    for member in targets:
        await throttle.put(member)
    await throttle.join()
    throttle.stop()
    return succeeded, failed


def make_roleall_command() -> app_commands.Command:  # type: ignore[type-arg]
    """Return a ready-to-add /roleall slash command."""

    @app_commands.command(
        name="roleall",
        description="Assign a role to all server members",
    )
    @app_commands.describe(
        role="Role to assign",
        filter_role="Only assign to members who already have this role",
    )
    @is_staff()
    async def roleall(
        interaction: discord.Interaction,
        role: discord.Role,
        filter_role: discord.Role | None = None,
    ) -> None:
        logger.debug(
            f"roleall: invoked by {interaction.user}, "
            f"role={role.name!r}, filter={filter_role and filter_role.name!r}"
        )
        await interaction.response.defer(thinking=True)

        guild = interaction.guild
        if guild is None:
            await interaction.followup.send(
                "This command must be used in a server.", ephemeral=True
            )
            return

        targets, already_have = _collect_targets(guild, role, filter_role)

        if not targets and not already_have:
            scope = (
                f"members with **{filter_role.name}**"
                if filter_role
                else "server members"
            )
            await interaction.followup.send(f"No {scope} found.")
            return

        if not targets:
            await interaction.followup.send(
                f"All eligible members already have **{role.name}**."
            )
            return

        eta = _format_duration(math.ceil(len(targets) / _ROLE_ASSIGN_RATE))
        await interaction.followup.send(
            f"Assigning **{role.name}** to **{len(targets)}** member(s) "
            f"— estimated time: **{eta}**."
        )

        succeeded, failed = await _assign_role_to_all(targets, role)

        lines: list[str] = [f"Assigned **{role.name}** to **{succeeded}** member(s)."]
        if already_have:
            lines.append(f"**{already_have}** already had the role.")
        if failed:
            lines.append(
                f"**{failed}** assignment(s) failed "
                "(check bot permissions and role hierarchy)."
            )
        if filter_role:
            lines.append(f"Filtered to members with **{filter_role.name}**.")

        await interaction.followup.send("\n".join(lines))

    @roleall.error
    async def roleall_error(
        interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await handle_check_failure(interaction, error)

    return roleall  # type: ignore[return-value]


def register_help(registry: HelpRegistry) -> None:
    """Register /roleall in the help registry."""
    registry.add_group(
        HelpGroup(
            name="roleall",
            description="Bulk role assignment",
            commands=[
                HelpEntry(
                    "/roleall <role> [filter_role]",
                    "Assign a role to all members, optionally filtered by another role",
                    "Staff",
                ),
            ],
        )
    )
