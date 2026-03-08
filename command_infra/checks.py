from __future__ import annotations

import os
from collections.abc import Callable
from typing import TypeVar

import discord
from discord import app_commands

T = TypeVar("T")


def _has_role(member: discord.Member, role_id: int) -> bool:
    return any(r.id == role_id for r in member.roles)


def is_staff() -> Callable[[T], T]:
    """Check: user must have the Staff role."""

    async def predicate(interaction: discord.Interaction) -> bool:
        if not isinstance(interaction.user, discord.Member):
            return False
        role_id_str = os.getenv("STAFF_ROLE_ID")
        if not role_id_str:
            return False
        return _has_role(interaction.user, int(role_id_str))

    return app_commands.check(predicate)  # type: ignore[return-value]


def is_senior_staff() -> Callable[[T], T]:
    """Check: user must have the Senior Staff role or Administrator permission."""

    async def predicate(interaction: discord.Interaction) -> bool:
        if not isinstance(interaction.user, discord.Member):
            return False
        if interaction.user.guild_permissions.administrator:
            return True
        role_id_str = os.getenv("SENIOR_STAFF_ROLE_ID")
        if not role_id_str:
            return False
        return _has_role(interaction.user, int(role_id_str))

    return app_commands.check(predicate)  # type: ignore[return-value]


async def handle_check_failure(
    interaction: discord.Interaction, error: app_commands.AppCommandError
) -> None:
    """Send a permission-denied message for CheckFailure errors."""
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message(
            "You don't have permission to use this command.", ephemeral=True
        )
