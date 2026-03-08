# core

Discord bot core — client setup, configuration, and service loading.

This package boots the bot, wires up every service, and provides the base classes that
all services extend.

## Key files

| File | Purpose |
|---|---|
| `discord_client.py` | `DiscordClient` — extends `discord.Client`, initialises all services on ready |
| `config.py` | `ConfigInterface` — typed access to environment variables |
| `service_loader.py` | Discovers and registers every service and its slash commands |
| `command_handler.py` | Singleton `CommandHandler` — owns the `app_commands.CommandTree` |
| `service_base.py` | `ServiceBase` — abstract base class for all feature services |
| `service_handler.py` | `ServiceHandler` — lifecycle management for registered services |
| `throttle.py` | Rate-limiting utilities used by services |
