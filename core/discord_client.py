from typing import override
import discord
from discord import app_commands
from loguru import logger

from core.command_handler import CommandHandler
from core.config import ConfigInterface, ConfigVars


class DiscordClient(discord.Client):
    def __init__(self, debug: bool = False) -> None:
        super().__init__(intents=discord.Intents.all())
        self.config: ConfigInterface = ConfigInterface()
        self._guild: discord.Guild | None = None
        self.debug: bool = debug
        self.command_handler: CommandHandler = CommandHandler(client=self)
        self._tree_ref: app_commands.CommandTree = self.command_handler.tree

    async def guild_setup(self) -> None:
        guild_id_str: str | None = self.config.get_variable(ConfigVars.GUILD_ID)
        if guild_id_str:
            self._guild = self.get_guild(int(guild_id_str))
            if self._guild:
                self.command_handler.guild = self._guild
                logger.info(f"Guild set to: {self._guild.name}")
            else:
                logger.error(f"Guild with ID {guild_id_str} not found")

    @override
    async def setup_hook(self) -> None:
        logger.info("Setting up client...")
        await self.guild_setup()

    async def on_ready(self) -> None:
        if not self.user:
            logger.error("Failed to connect.")
            return
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logger.info(await self.command_handler.sync())

    @property
    def current_guild(self) -> discord.Guild | None:
        if not self._guild:
            raise RuntimeError("Guild not set")
        return self._guild

    @property
    def tree(self) -> app_commands.CommandTree:
        if not self._tree_ref:
            raise RuntimeError("Command Initialization Failed / Not started.")
        return self._tree_ref
