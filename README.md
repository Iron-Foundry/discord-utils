# Iron Foundry - Discord Utils

Utility bot for the Iron Foundry OSRS clan. Handles temporary voice channels, music
playback, clan content image generation, and the clan event/chat relay.

---

## Requirements

- Python 3.14+
- [uv](https://docs.astral.sh/uv/) (package manager)
- A running PostgreSQL instance shared with `discord-server`
- A running Valkey/Redis instance
- A Lavalink v4 node (music only - optional)

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
| `DEBUG_MODE` | - | Enable debug logging. |
| `MUSIC_BOT_TOKENS` | - | Comma-separated player bot tokens, max 5. The count is the music pool size; blank disables music. |
| `LAVALINK_URI` | `http://localhost:2333` | Lavalink v4 node base URL. |
| `LAVALINK_PASSWORD` | - | Lavalink node password. Required when `MUSIC_BOT_TOKENS` is set. |
| `API_BACKEND_URL` | - | api-backend base URL. Needed to read saved playlists; without it the playlist controls are absent. |
| `METRICS_API_KEY` | - | Shared service key sent as `verification-code` when reading playlists. |

---

## Commands

| Group | Description |
|---|---|
| `/tempvc` | Configure temporary voice channels - trigger channel setup and GIM group management. |
| `/whitelist` | Manage your temporary voice channel whitelist. |
| `/otw` | Generate a styled OSRS Of The Week image for one, two, or three categories. |
| `/chatevents` | Configure the channel for clan event and chat relay messages. |
| `/clanstats` | Post clan statistics. |
| `/roleall` | Bulk role assignment. |
| `/testevent` | Emit a test clan event through the relay. |
| `/help` | Browse the registered command groups. |

Music commands register at the top level (not under a `/music` group) and only when
`MUSIC_BOT_TOKENS` is set: `/play`, `/pause`, `/resume`, `/skip`, `/stop`, `/seek`,
`/queue`, `/nowplaying`, `/remove`, `/shuffle`, `/loop`, `/volume`, `/playlist`.

---

## Architecture

```
core/
  discord_client.py   - DiscordClient: event handling and startup orchestration
  service_loader.py   - async functions that initialise each service; OTW registered after
  command_handler.py  - CommandHandler singleton, owns the slash-command tree
  config.py           - ConfigInterface, env-var access
  service_base.py     - Service abstract base class
  service_handler.py  - ServiceHandler lifecycle manager
  throttle.py         - rate limiting helpers
  db/                 - PostgreSQL engine and session management

command_infra/        - checks, /help registry, and the standalone commands
                        (otw, clanstats, roleall, testevent)
temp_vc/              - Temporary voice channel service and repository
imagegen/             - PIL-based image renderer for OTW images
  assets/             - Fonts, skill/boss icons, and background image
music/                - Lavalink v4 music service: player-bot pool, queue, playlists,
                        panel views, and the Valkey bridge to api-backend
chat_events/          - Clan event and chat relay
```

---

## Development

```bash
uv run ruff format .
uv run ruff check . --fix
uv run pyright
uv run pytest
```

Tests live in `tests/` - unit and contract tests at the top level, real-infra tests
under `tests/integration/`. From the monorepo root, `./run-tests.sh` runs them
alongside the other services.
