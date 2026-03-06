from __future__ import annotations

from typing import Any

import discord
from loguru import logger

from core.service_base import Service
from temp_vc.models import TempVCConfig
from temp_vc.repository import MongoTempVCRepository

TRIGGER_CHANNEL_NAME = "➕ Create VC"


class TempVCService(Service):
    """Manages on-demand temporary voice channels."""

    def __init__(self, guild: discord.Guild, repo: MongoTempVCRepository) -> None:
        self._guild = guild
        self._repo = repo
        self._config: TempVCConfig | None = None

    async def initialize(self) -> None:
        """Load config from DB, ensure indexes, and restore trigger channel if missing."""
        await self._repo.ensure_indexes()
        self._config = await self._repo.get_config(self._guild.id)
        if self._config is None:
            self._config = TempVCConfig(guild_id=self._guild.id)
        await self._ensure_trigger()
        logger.info("TempVCService: initialized")

    async def post_ready(self) -> None:
        """Called after on_ready with the live guild cache.

        Validates persisted active channels: removes entries whose voice
        channels no longer exist, and deletes channels that are now empty.
        The live guild is required because setup_hook only has a REST snapshot
        without populated voice state or member caches.
        """
        if not self._config or not self._config.active_channels:
            return

        stale: list[int] = []
        empty: list[int] = []

        for owner_id, channel_id in list(self._config.active_channels.items()):
            channel = self._guild.get_channel(channel_id)
            if not isinstance(channel, discord.VoiceChannel):
                stale.append(owner_id)
            elif len(channel.members) == 0:
                empty.append(channel_id)

        # Remove stale map entries (channel deleted while bot was offline)
        for owner_id in stale:
            self._config.active_channels.pop(owner_id, None)

        if stale:
            await self._repo.save_config(self._config)
            logger.info(f"TempVCService: removed {len(stale)} stale active channel(s)")

        # Delete and clean up channels that are now empty
        for channel_id in empty:
            await self.cleanup_channel(channel_id)

        if empty:
            logger.info(
                f"TempVCService: cleaned up {len(empty)} empty active channel(s)"
            )

    # ------------------------------------------------------------------
    # Trigger channel management
    # ------------------------------------------------------------------

    @property
    def trigger_channel_id(self) -> int | None:
        """The ID of the trigger voice channel."""
        return self._config.trigger_channel_id if self._config else None

    async def create_trigger_channel(
        self, category: discord.CategoryChannel
    ) -> discord.VoiceChannel:
        """Create the trigger voice channel in a category and persist it."""
        assert self._config is not None
        channel = await category.create_voice_channel(name=TRIGGER_CHANNEL_NAME)
        self._config.trigger_channel_id = channel.id
        self._config.trigger_channel_category_id = category.id
        await self._repo.save_config(self._config)
        logger.info(f"TempVCService: trigger channel created ({channel.id})")
        return channel

    async def handle_trigger_deleted(self, channel_id: int) -> None:
        """Called when a channel is deleted — recreates trigger if it was deleted."""
        if self._config is None or self._config.trigger_channel_id != channel_id:
            return
        self._config.trigger_channel_id = None
        await self._recreate_trigger()

    async def _ensure_trigger(self) -> None:
        """Recreate the trigger channel on startup if it no longer exists."""
        if self._config is None or self._config.trigger_channel_id is None:
            return
        channel = self._guild.get_channel(self._config.trigger_channel_id)
        if channel is None:
            logger.warning("TempVCService: trigger channel missing, recreating")
            await self._recreate_trigger()

    async def _recreate_trigger(self) -> None:
        """Recreate the trigger channel in the stored category."""
        if self._config is None or self._config.trigger_channel_category_id is None:
            logger.warning("TempVCService: no category stored, cannot recreate trigger")
            return
        category = self._guild.get_channel(self._config.trigger_channel_category_id)
        if not isinstance(category, discord.CategoryChannel):
            logger.error("TempVCService: stored category no longer exists")
            return
        try:
            channel = await category.create_voice_channel(name=TRIGGER_CHANNEL_NAME)
            self._config.trigger_channel_id = channel.id
            await self._repo.save_config(self._config)
            logger.info(f"TempVCService: trigger channel recreated ({channel.id})")
        except discord.HTTPException as e:
            logger.error(f"TempVCService: failed to recreate trigger channel: {e}")

    # ------------------------------------------------------------------
    # GIM role management
    # ------------------------------------------------------------------

    async def add_gim_role(self, role_id: int) -> bool:
        """Add a GIM role. Returns True if added, False if already present."""
        assert self._config is not None
        if role_id in self._config.gim_role_ids:
            return False
        self._config.gim_role_ids.append(role_id)
        await self._repo.save_config(self._config)
        return True

    async def remove_gim_role(self, role_id: int) -> bool:
        """Remove a GIM role. Returns True if removed, False if not found."""
        assert self._config is not None
        if role_id not in self._config.gim_role_ids:
            return False
        self._config.gim_role_ids.remove(role_id)
        await self._repo.save_config(self._config)
        return True

    @property
    def gim_role_ids(self) -> list[int]:
        """Return the list of configured GIM role IDs."""
        return list(self._config.gim_role_ids) if self._config else []

    def get_gim_roles(self, member: discord.Member) -> list[discord.Role]:
        """Return the GIM roles the member has from the configured list."""
        if self._config is None:
            return []
        return [r for r in member.roles if r.id in self._config.gim_role_ids]

    # ------------------------------------------------------------------
    # Channel state helpers
    # ------------------------------------------------------------------

    def is_trigger(self, channel_id: int) -> bool:
        """Return True if the channel is the configured trigger channel."""
        return (
            self._config is not None and self._config.trigger_channel_id == channel_id
        )

    def is_active(self, channel_id: int) -> bool:
        """Return True if the channel is a tracked temp VC."""
        if self._config is None:
            return False
        return channel_id in self._config.active_channels.values()

    def has_active_channel(self, member_id: int) -> bool:
        """Return True if the member already owns a temp VC."""
        if self._config is None:
            return False
        return member_id in self._config.active_channels

    def get_active_channel_id(self, member_id: int) -> int | None:
        """Return the active temp VC channel ID for the member, or None."""
        if self._config is None:
            return None
        return self._config.active_channels.get(member_id)

    def get_owner_id(self, channel_id: int) -> int | None:
        """Return the owner ID for an active channel, or None."""
        if self._config is None:
            return None
        for owner_id, ch_id in self._config.active_channels.items():
            if ch_id == channel_id:
                return owner_id
        return None

    # ------------------------------------------------------------------
    # Channel lifecycle
    # ------------------------------------------------------------------

    async def create_channel(
        self, member: discord.Member
    ) -> discord.VoiceChannel | None:
        """Create a default temp VC named after the member and move them in."""
        assert self._config is not None

        # Determine category from trigger channel
        category: discord.CategoryChannel | None = None
        if self._config.trigger_channel_id:
            trigger = self._guild.get_channel(self._config.trigger_channel_id)
            if isinstance(trigger, discord.VoiceChannel):
                category = trigger.category

        try:
            channel = await self._guild.create_voice_channel(
                name=member.display_name,
                user_limit=0,
                category=category,
                reason=f"Temp VC for {member.display_name}",
            )
        except discord.HTTPException as e:
            logger.error(f"TempVCService: failed to create channel for {member}: {e}")
            return None

        self._config.active_channels[member.id] = channel.id
        await self._repo.save_config(self._config)

        try:
            await member.move_to(channel, reason="Moving to temp VC")
        except discord.HTTPException as e:
            logger.warning(f"TempVCService: could not move {member}: {e}")

        logger.info(
            f"TempVCService: created channel {channel.name!r} for {member.display_name}"
        )
        return channel

    async def configure_channel(
        self,
        channel_id: int,
        name: str | None,
        user_limit: int,
    ) -> None:
        """Edit an existing temp VC's name and/or user limit."""
        channel = self._guild.get_channel(channel_id)
        if not isinstance(channel, discord.VoiceChannel):
            return
        kwargs: dict[str, Any] = {"user_limit": user_limit}
        if name:
            kwargs["name"] = name
        try:
            await channel.edit(**kwargs)
        except discord.HTTPException as e:
            logger.error(
                f"TempVCService: failed to configure channel {channel_id}: {e}"
            )

    async def gim_channel(self, channel_id: int, role_name: str) -> None:
        """Rename an existing temp VC to a GIM role name."""
        channel = self._guild.get_channel(channel_id)
        if not isinstance(channel, discord.VoiceChannel):
            return
        try:
            await channel.edit(name=role_name)
        except discord.HTTPException as e:
            logger.error(f"TempVCService: failed to rename channel {channel_id}: {e}")

    async def cleanup_channel(self, channel_id: int) -> None:
        """Delete an empty temp VC and remove it from the active map."""
        assert self._config is not None
        owner_id = self.get_owner_id(channel_id)
        channel = self._guild.get_channel(channel_id)

        if isinstance(channel, discord.VoiceChannel):
            try:
                await channel.delete(reason="Temp VC is empty")
            except discord.HTTPException as e:
                logger.error(
                    f"TempVCService: failed to delete channel {channel_id}: {e}"
                )

        if owner_id is not None:
            self._config.active_channels.pop(owner_id, None)
            await self._repo.save_config(self._config)

        logger.info(f"TempVCService: cleaned up channel {channel_id}")
