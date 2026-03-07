"""Pure service-loading functions; no access to DiscordClient internals."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from loguru import logger

from commands.help_registry import HelpRegistry

if TYPE_CHECKING:
    from core.discord_client import DiscordClient
    from temp_vc.service import TempVCService


async def load_temp_vc_service(
    guild: discord.Guild,
    tree: app_commands.CommandTree,
    registry: HelpRegistry,
    mongo_uri: str,
    db_name: str,
    client: DiscordClient,
) -> TempVCService:
    """Initialise the temp VC service and register its slash commands."""
    from commands.temp_vc import TempVCGroup, register_help
    from temp_vc.events import register as register_temp_vc_events
    from temp_vc.repository import MongoTempVCRepository
    from temp_vc.service import TempVCService

    repo = MongoTempVCRepository(mongo_uri=mongo_uri, db_name=db_name)
    service = TempVCService(guild=guild, repo=repo)
    await service.initialize()

    register_temp_vc_events(service, client)
    register_help(registry)
    tree.add_command(TempVCGroup(service=service), guild=guild)
    logger.info("Temp VC service initialised and commands registered")
    return service


def _register_otw_commands(
    guild: discord.Guild,
    tree: app_commands.CommandTree,
    registry: HelpRegistry,
) -> None:
    """Register the /otw command (stateless, no DB) and its help entry."""
    from commands.help_registry import HelpEntry, HelpGroup
    from commands.otw import make_otw_command

    tree.add_command(make_otw_command(), guild=guild)
    registry.add_group(
        HelpGroup(
            name="otw",
            description="Generate Of The Week announcement images",
            commands=[
                HelpEntry(
                    "/otw <date> [skill] [boss] [raid]",
                    "Generate a Skill/Boss/Raid of the Week image",
                    "Staff",
                ),
            ],
        )
    )
    logger.info("OTW command registered")


def _load_help_command(
    guild: discord.Guild,
    tree: app_commands.CommandTree,
    registry: HelpRegistry,
) -> None:
    from commands.help import make_help_command, register_help

    register_help(registry)
    tree.add_command(make_help_command(registry), guild=guild)
    logger.info("Help command registered")


def _register_clan_stats_commands(
    guild: discord.Guild,
    tree: app_commands.CommandTree,
    registry: HelpRegistry,
) -> None:
    """Register the /clanstats command (stateless, no DB) and its help entry."""
    from commands.clan_stats import make_clan_stats_command, register_help

    tree.add_command(make_clan_stats_command(), guild=guild)
    register_help(registry)
    logger.info("Clan stats command registered")


async def load_all_services(
    guild: discord.Guild,
    tree: app_commands.CommandTree,
    registry: HelpRegistry,
    client: DiscordClient,
    mongo_uri: str,
    db_name: str,
) -> tuple[TempVCService]:
    """Load all services in parallel, then register stateless commands and /help."""
    (temp_vc,) = await asyncio.gather(
        load_temp_vc_service(guild, tree, registry, mongo_uri, db_name, client),
    )
    _register_otw_commands(guild, tree, registry)
    _register_clan_stats_commands(guild, tree, registry)
    _load_help_command(guild, tree, registry)
    return (temp_vc,)
