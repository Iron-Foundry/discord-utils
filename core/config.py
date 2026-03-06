from enum import Enum
from dotenv import load_dotenv
from loguru import logger
import os


class ConfigVars(str, Enum):
    """Environment variable keys"""

    DISCORD_TOKEN = "DISCORD_TOKEN"
    GUILD_ID = "GUILD_ID"
    DEBUG_MODE = "DEBUG_MODE"
    MONGO_URI = "MONGO_URI"
    MONGO_DB_NAME = "MONGO_DB_NAME"
    STAFF_ROLE_ID = "STAFF_ROLE_ID"
    SENIOR_STAFF_ROLE_ID = "SENIOR_STAFF_ROLE_ID"


class ConfigInterface:
    """Interface class for handling environment variable loading"""

    def __init__(self) -> None:
        load_dotenv()

    def load_environment(self) -> None:
        logger.info("Reloading Environment")
        load_dotenv()

    def get_variable(self, variable: "ConfigVars | str") -> str | None:
        key = variable.value if isinstance(variable, ConfigVars) else variable
        logger.info(f"Fetching environment variable: {key}")
        return os.getenv(key, None)
