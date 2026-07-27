"""Test event command - manually insert a fake event row for a member."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import discord
from discord import app_commands
from loguru import logger

from command_infra.checks import handle_check_failure, is_senior_staff
from command_infra.help_registry import HelpEntry, HelpGroup, HelpRegistry

_EVENT_TYPES = [
    app_commands.Choice(name="Drop (loot)", value="loot"),
    app_commands.Choice(name="Level Up", value="level"),
    app_commands.Choice(name="XP Milestone", value="xp_milestone"),
    app_commands.Choice(name="Quest", value="quest"),
    app_commands.Choice(name="Diary", value="diary"),
    app_commands.Choice(name="Combat Achievement", value="combat_achievement"),
    app_commands.Choice(name="Pet", value="pet"),
    app_commands.Choice(name="Collection Log", value="collection_log"),
    app_commands.Choice(name="Clue Item", value="clue_item"),
    app_commands.Choice(name="Personal Best", value="personal_best"),
    app_commands.Choice(name="HCIM Death", value="hcim_death"),
    app_commands.Choice(name="Loot Key", value="loot_key"),
]


def _build_data(
    event_type: str,
    name: str | None,
    value: int | None,
    source: str | None,
    player_name: str,
) -> dict[str, Any]:
    """Build a minimal data payload for the given event type."""
    match event_type:
        case "loot":
            return {
                "item_name": name or "Twisted bow",
                "source": source or "Chambers of Xeric",
                "coin_value": value or 1_000_000_000,
            }
        case "level":
            return {
                "skill": name or "Attack",
                "new_level": value or 99,
            }
        case "xp_milestone":
            return {
                "skill": name or "Attack",
                "xp": value or 13_034_431,
            }
        case "quest":
            return {
                "name": name or "Dragon Slayer II",
                "achievement_type": "quest",
            }
        case "diary":
            return {
                "name": name or "Lumbridge & Draynor Elite",
                "achievement_type": "diary",
            }
        case "combat_achievement":
            return {
                "name": name or "Inferno",
                "achievement_type": "combat_achievement",
            }
        case "pet":
            return {
                "pet_name": name or "Olmlet",
            }
        case "collection_log":
            return {
                "item_name": name or "Twisted bow",
                "log_slots": value or 750,
                "log_slots_max": 1508,
            }
        case "clue_item":
            return {
                "item_name": name or "Ranger boots",
                "coin_value": value or 40_000_000,
            }
        case "personal_best":
            return {
                "activity": name or "Chambers of Xeric",
                "variant": source,
                "time_seconds": value or 1380,
            }
        case "hcim_death":
            return {}
        case "loot_key":
            return {
                "coin_value": value or 5_000_000,
            }
        case _:
            return {}


async def _get_rsn(discord_user_id: int) -> str | None:
    """Return the member's linked RSN, or None."""
    from core.db.engine import get_session_factory
    from core.db.models import User

    async with get_session_factory()() as session:
        row = await session.get(User, discord_user_id)
    return row.rsn if row else None


async def _insert_event(
    event_type: str,
    player_name: str,
    user_id: int,
    data: dict[str, Any],
) -> int:
    """Insert an event row and return its new id."""
    from core.db.engine import get_session_factory
    from core.db.models import Event

    event = Event(
        type=event_type,
        timestamp=datetime.now(UTC),
        player_name=player_name,
        data=data,
        user_id=user_id,
    )
    async with get_session_factory()() as session:
        session.add(event)
        await session.flush()
        event_id = event.id
        await session.commit()
    return event_id


def make_test_event_command() -> app_commands.Command[Any, Any, Any]:
    """Return a ready-to-add /testevent slash command."""

    @app_commands.command(
        name="testevent",
        description="[Dev] Insert a fake event for a member to test the activity feed",
    )
    @app_commands.describe(
        member="The Discord member to attach the event to",
        event_type="Type of event to create",
        name="Item / skill / quest / activity name (uses a default if omitted)",
        value="Numeric value: coin amount, level, xp, time in seconds (uses a default if omitted)",
        source="Source for drops, or variant for personal bests (optional)",
    )
    @app_commands.choices(event_type=_EVENT_TYPES)
    @is_senior_staff()
    async def testevent(
        interaction: discord.Interaction,
        member: discord.Member,
        event_type: app_commands.Choice[str],
        name: str | None = None,
        value: int | None = None,
        source: str | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)

        rsn = await _get_rsn(member.id)
        if not rsn:
            await interaction.followup.send(
                f"{member.mention} has no linked RSN - link one first via `/settings`.",
                ephemeral=True,
            )
            return

        data = _build_data(event_type.value, name, value, source, rsn)
        event_id = await _insert_event(event_type.value, rsn, member.id, data)

        logger.info(
            "testevent: inserted {} event #{} for {} (rsn={!r}) by {}",
            event_type.value,
            event_id,
            member,
            rsn,
            interaction.user,
        )

        embed = discord.Embed(
            title="Test event inserted",
            color=discord.Color.green(),
        )
        embed.add_field(name="Member", value=member.mention, inline=True)
        embed.add_field(name="RSN", value=rsn, inline=True)
        embed.add_field(name="Type", value=event_type.name, inline=True)
        embed.add_field(name="Event ID", value=str(event_id), inline=True)
        embed.add_field(
            name="Data",
            value=f"```json\n{json.dumps(data, indent=2)}\n```",
            inline=False,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @testevent.error
    async def testevent_error(
        interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.CheckFailure):
            await handle_check_failure(interaction, error)
            return
        logger.exception("testevent: unhandled error", exc_info=error)
        msg = f"Error: {error.__cause__ or error}"
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)

    return testevent


def register_help(registry: HelpRegistry) -> None:
    """Register /testevent in the help registry."""
    registry.add_group(
        HelpGroup(
            name="testevent",
            description="Dev tool - insert fake events for feed testing",
            commands=[
                HelpEntry(
                    "/testevent <member> <type> [name] [value] [source]",
                    "Insert a fake event for a member's activity feed",
                    "Senior Staff",
                ),
            ],
        )
    )
