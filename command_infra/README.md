# command_infra

Slash command infrastructure — checks, help system, and standalone commands.

Nothing here defines a feature service; this folder holds the shared plumbing that all
service commands rely on, plus a handful of simple standalone commands.

## Key files

| File | Purpose |
|---|---|
| `checks.py` | Permission check decorators (`is_staff`, `is_senior_staff`) and failure handler |
| `help_registry.py` | `HelpRegistry` — collects `HelpEntry`/`HelpGroup` objects from every service |
| `help.py` | `/help` slash command — renders the registry into an embed |
| `otw.py` | `/otw` command — posts the Of The Week image for a given category |
| `clan_stats.py` | `/clan-stats` command — fetches and displays clan hiscores |
| `role_all.py` | `/role-all` command — bulk-assigns a role to all current members |
