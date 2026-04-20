from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from loguru import logger

if TYPE_CHECKING:
    from core.discord_client import DiscordClient
    from temp_vc.service import TempVCService


# ---------------------------------------------------------------------------
# Modals
# ---------------------------------------------------------------------------


class TempVCConfigureModal(discord.ui.Modal, title="Configure Your Channel"):
    """Modal for renaming and setting a user limit on an existing temp VC."""

    name = discord.ui.TextInput(
        label="Channel name",
        required=False,
        max_length=30,
        placeholder="Leave blank to keep current name",
    )
    limit = discord.ui.TextInput(
        label="User limit (0 = unlimited)",
        required=False,
        max_length=2,
        placeholder="0–99, leave blank for unlimited",
    )

    def __init__(
        self,
        service: TempVCService,
        channel_id: int,
        original_msg: discord.Message,
    ) -> None:
        super().__init__()
        self._service = service
        self._channel_id = channel_id
        self._original_msg = original_msg

    async def on_submit(self, interaction: discord.Interaction) -> None:
        name = self.name.value.strip() or None
        try:
            user_limit = max(0, min(99, int(self.limit.value.strip() or "0")))
        except ValueError:
            user_limit = 0

        logger.debug(
            f"TempVC: configure modal submitted - name={name!r}, limit={user_limit}"
        )
        await self._service.configure_channel(self._channel_id, name, user_limit)
        await interaction.response.defer()
        try:
            await self._original_msg.edit(content="✅ Channel configured!", view=None)
        except discord.HTTPException:
            pass


# ---------------------------------------------------------------------------
# DM view shown after channel creation
# ---------------------------------------------------------------------------


class TempVCDMView(discord.ui.View):
    """Sent as a DM after the temp VC is created, letting the member customise it."""

    def __init__(
        self,
        service: TempVCService,
        channel_id: int,
        private: bool = False,
    ) -> None:
        super().__init__(timeout=120)
        self._service = service
        self._channel_id = channel_id
        self._private = private
        self._sync_privacy_button()

    def _sync_privacy_button(self) -> None:
        """Update the privacy button label and style to match current state."""
        for item in self.children:
            if (
                isinstance(item, discord.ui.Button)
                and item.custom_id == "toggle_privacy"
            ):
                if self._private:
                    item.label = "🔓 Make Public"
                    item.style = discord.ButtonStyle.red
                else:
                    item.label = "🔒 Make Private"
                    item.style = discord.ButtonStyle.secondary
                break

    # ------------------------------------------------------------------
    # Auto - keep the channel as-is
    # ------------------------------------------------------------------

    @discord.ui.button(label="Auto", style=discord.ButtonStyle.green)
    async def auto(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        logger.debug(f"TempVC: Auto selected by {interaction.user}")
        await interaction.response.edit_message(
            content="✅ Your voice channel is ready!", view=None
        )
        self.stop()

    # ------------------------------------------------------------------
    # Configure - rename / set user limit via modal
    # ------------------------------------------------------------------

    @discord.ui.button(label="Configure", style=discord.ButtonStyle.blurple)
    async def configure(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        msg = interaction.message
        if msg is None:
            await interaction.response.send_message(
                "Something went wrong.", ephemeral=True
            )
            return
        await interaction.response.send_modal(
            TempVCConfigureModal(
                service=self._service,
                channel_id=self._channel_id,
                original_msg=msg,
            )
        )
        self.stop()

    # ------------------------------------------------------------------
    # Privacy toggle - make the channel private or public
    # ------------------------------------------------------------------

    @discord.ui.button(
        label="🔒 Make Private",
        style=discord.ButtonStyle.secondary,
        custom_id="toggle_privacy",
    )
    async def toggle_privacy(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self._private = not self._private
        logger.debug(
            f"TempVC: privacy toggled to {self._private!r} by {interaction.user}"
        )
        await self._service.toggle_privacy(
            interaction.user.id, self._channel_id, self._private
        )
        self._sync_privacy_button()
        status = "private 🔒" if self._private else "public 🔓"
        await interaction.response.edit_message(
            content=(
                f"🎤 **Your voice channel has been created!**\n"
                f"Channel is now **{status}**. Choose how you'd like to set it up:"
            ),
            view=self,
        )


# ---------------------------------------------------------------------------
# Event registration
# ---------------------------------------------------------------------------


def register(service: TempVCService, client: DiscordClient) -> None:
    """Register voice state and channel delete events for temp VC management."""

    async def on_voice_state_update(
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        # Cleanup: member left an active temp VC that is now empty
        if before.channel and service.is_active(before.channel.id):
            if len(before.channel.members) == 0:
                logger.debug(
                    f"TempVC: channel {before.channel.id} is empty, cleaning up"
                )
                await service.cleanup_channel(before.channel.id)

        # Creation: member joined the trigger channel
        if not (after.channel and service.is_trigger(after.channel.id)):
            return

        logger.debug(
            f"TempVC: {member.display_name} joined trigger channel {after.channel.id}"
        )

        # If they already own a channel, redirect them there
        if service.has_active_channel(member.id):
            existing_id = service.get_active_channel_id(member.id)
            if existing_id is not None:
                existing = member.guild.get_channel(existing_id)
                if isinstance(existing, discord.VoiceChannel):
                    logger.debug(
                        f"TempVC: {member.display_name} already has channel"
                        f" {existing_id}, redirecting"
                    )
                    try:
                        await member.move_to(existing, reason="Already has temp VC")
                    except discord.HTTPException:
                        pass
            return

        channel = await service.create_channel(member)
        if channel is None:
            return

        user_settings = await service.get_user_settings(member.id)
        logger.debug(
            f"TempVC: sending DM to {member.display_name},"
            f" private={user_settings.private}"
        )
        view = TempVCDMView(
            service=service,
            channel_id=channel.id,
            private=user_settings.private,
        )
        status = "private 🔒" if user_settings.private else "public 🔓"
        try:
            await member.send(
                f"🎤 **Your voice channel has been created!**\n"
                f"Channel is **{status}**. Choose how you'd like to set it up:",
                view=view,
            )
        except discord.Forbidden:
            logger.debug(f"TempVC: DM blocked for {member}, channel stays as-is")
        except discord.HTTPException as e:
            logger.error(f"TempVC: failed to DM {member}: {e}")

    async def on_guild_channel_delete(channel: discord.abc.GuildChannel) -> None:
        await service.handle_trigger_deleted(channel.id)

    client.add_listener(on_voice_state_update, "on_voice_state_update")
    client.add_listener(on_guild_channel_delete, "on_guild_channel_delete")
