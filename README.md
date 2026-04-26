# Iron Foundry - Discord Utils

Utility bot for the Iron Foundry OSRS clan. Handles temporary voice channels and
clan content image generation.

---

## Requirements

- Python 3.14+
- [uv](https://docs.astral.sh/uv/) (package manager)
- A running MongoDB instance shared with `discord-server`

---

## Setup

1. Clone the repository and install dependencies:

   ```bash
   uv sync
   ```

2. Copy `.env.example` to `.env` and fill in the values (see [Environment Variables](#environment-variables) below).

3. Run the bot:

   ```bash
   uv run python main.py
   ```

---

## Environment Variables

All configuration is read from a `.env` file in the project root.

### Required

| Variable | Description |
|---|---|
| `DISCORD_TOKEN` | Bot token from the Discord Developer Portal. |
| `GUILD_ID` | The ID of the Discord server the bot operates in. |
| `DATABASE_URL` | PostgreSQL connection string. |
| `STAFF_ROLE_ID` | Role ID for Staff. |
| `SENIOR_STAFF_ROLE_ID` | Role ID for Senior Staff. |

### Optional

| Variable | Default | Description |
|---|---|---|
| `VALKEY_URI` | `redis://localhost:6379` | Valkey/Redis connection string. |
| `DEBUG_MODE` | — | Enable debug logging. |

---

## Commands

| Group | Description |
|---|---|
| `/tempvc` | Configure temporary voice channels — trigger channel setup and GIM group management. |
| `/otw` | Generate a styled OSRS Of The Week image for one, two, or three categories. |
| `/chatevents` | Configure the channel for clan event and chat relay messages. |

---

## Architecture

```
core/
  discord_client.py   - DiscordClient: event handling and startup orchestration
  service_loader.py   - async functions that initialise each service; OTW registered after
  command_handler.py  - CommandHandler singleton, owns the slash-command tree
  config.py           - ConfigInterface, env-var access

temp_vc/              - Temporary voice channel service and repository
imagegen/             - PIL-based image renderer for OTW images
  assets/             - Fonts, skill/boss icons, and background image
commands/             - Slash command definitions
```

---

## Development

```bash
uv run ruff check .
uv run ruff format .
```
