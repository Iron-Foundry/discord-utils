# Iron Foundry — Discord Utils

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
| `MONGO_URI` | MongoDB connection string. Must point to the same instance as `discord-server`. |
| `STAFF_ROLE_ID` | Role ID for Staff. Required for staff-gated commands. |
| `SENIOR_STAFF_ROLE_ID` | Role ID for Senior Staff. Required for senior-staff-gated commands. |

### Optional

| Variable | Default | Description |
|---|---|---|
| `MONGO_DB_NAME` | `foundry` | MongoDB database name. Must match `discord-server`. |
| `DEBUG_MODE` | — | Set to any truthy value to enable debug logging. |

---

## Commands

### /tempvc

Manage the temporary voice channel feature. When a member joins the trigger channel,
a private voice channel is created for them automatically.

| Command | Description | Access |
|---|---|---|
| `/tempvc setup <category>` | Create the trigger voice channel in a category. | Senior Staff |
| `/tempvc gim add <role>` | Add a role as a GIM group. | Senior Staff |
| `/tempvc gim remove <role>` | Remove a role from GIM groups. | Senior Staff |
| `/tempvc gim list` | List all configured GIM group roles. | Staff |

After a channel is created, the owner receives a DM letting them name it, set a user
limit, or rename it to their GIM team.

### /otw

Generate a styled OSRS-themed image for the Of The Week announcement. Accepts one,
two, or three entries (skill, boss, raid) and renders the appropriate single, double,
or triple layout.

| Command | Description | Access |
|---|---|---|
| `/otw <date> [skill] [boss] [raid]` | Generate an Of The Week image and post it. | Staff |

All three content parameters support autocomplete. At least one must be provided.

---

## Architecture

```
core/
  discord_client.py   — DiscordClient: event handling and startup orchestration
  service_loader.py   — async functions that initialise each service; OTW registered after
  command_handler.py  — CommandHandler singleton, owns the slash-command tree
  config.py           — ConfigInterface, env-var access

temp_vc/              — Temporary voice channel service and repository
imagegen/             — PIL-based image renderer for OTW images
  assets/             — Fonts, skill/boss icons, and background image
commands/             — Slash command definitions
```

On startup `setup_hook` calls `load_all_services`, which initialises the TempVC
service and then registers the stateless `/otw` command.

---

## Development

Run the linter and formatter:

```bash
uv run ruff check .
uv run ruff format .
```
