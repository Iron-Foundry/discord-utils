"""Pure service-loading functions; no access to DiscordClient internals."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from loguru import logger

if TYPE_CHECKING:
    from core.discord_client import DiscordClient
    from temp_vc.service import TempVCService


async def load_temp_vc_service(
    guild: discord.Guild,
    tree: app_commands.CommandTree,
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
    register_help()
    tree.add_command(TempVCGroup(service=service), guild=guild)
    logger.info("Temp VC service initialised and commands registered")
    return service


def register_otw_commands(
    guild: discord.Guild,
    tree: app_commands.CommandTree,
) -> None:
    """Register the /otw command (stateless, no DB)."""
    from commands.otw import make_otw_command

    tree.add_command(make_otw_command(), guild=guild)
    logger.info("OTW command registered")


async def load_all_services(
    guild: discord.Guild,
    tree: app_commands.CommandTree,
    client: DiscordClient,
    mongo_uri: str,
    db_name: str,
) -> tuple[TempVCService]:
    """Load all services in parallel."""
    (temp_vc,) = await asyncio.gather(
        load_temp_vc_service(guild, tree, mongo_uri, db_name, client),
    )
    register_otw_commands(guild, tree)
    return (temp_vc,)
