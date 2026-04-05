from pydantic import BaseModel


class ClanEventsConfig(BaseModel):
    """Persisted configuration for the clan events service."""

    guild_id: int
    channel_id: int | None = None  # single channel for all event types and chat relay
