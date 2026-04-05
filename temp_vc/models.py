from pydantic import BaseModel, Field


class TempVCConfig(BaseModel):
    """Persisted configuration for the temp VC service."""

    guild_id: int
    trigger_channel_id: int | None = None
    trigger_channel_category_id: int | None = None
    active_channels: dict[int, int] = Field(
        default_factory=dict
    )  # owner_id → channel_id


class TempVCUserSettings(BaseModel):
    """Persisted per-user settings for the temp VC service."""

    user_id: int
    guild_id: int
    private: bool = False
    whitelist: list[int] = Field(default_factory=list)  # member IDs allowed to connect
