from pydantic import BaseModel, Field


class TempVCConfig(BaseModel):
    """Persisted configuration for the temp VC service."""

    guild_id: int
    trigger_channel_id: int | None = None
    trigger_channel_category_id: int | None = None
    gim_role_ids: list[int] = Field(default_factory=list)
    active_channels: dict[int, int] = Field(
        default_factory=dict
    )  # owner_id → channel_id
