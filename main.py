import asyncio

from loguru import logger

from core.discord_client import DiscordClient
from core.config import ConfigInterface, ConfigVars


async def main():
    logger.info("Starting Service: Discord-Utils")
    config = ConfigInterface()
    discord_token = config.get_variable(ConfigVars.DISCORD_TOKEN)
    debug_mode = config.get_variable(ConfigVars.DEBUG_MODE)

    if discord_token is None:
        logger.warning("Environment file or DISCORD_TOKEN key missing.")
        exit(code=1)

    client = DiscordClient(debug=debug_mode == "true")
    await client.start(token=discord_token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting Down Discord-Utils")
        exit(code=0)
