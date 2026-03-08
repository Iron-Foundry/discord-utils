# temp_vc

Temporary voice channel service — creates a private per-user VC when a member joins a
designated trigger channel, then deletes it automatically when it empties.

## Key files

| File | Purpose |
|---|---|
| `service.py` | `TempVcService` — main service, handles VC creation and cleanup |
| `events.py` | Voice state update event listener |
| `commands.py` | `/temp-vc` slash commands (configure trigger channel, list active VCs) |
| `models.py` | Pydantic models for VC config and state |
| `repository.py` | MongoDB persistence for active temporary channels |
