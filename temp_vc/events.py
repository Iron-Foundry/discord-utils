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
            f"TempVC: configure modal submitted — name={name!r}, limit={user_limit}"
        )
        await self._service.configure_channel(self._channel_id, name, user_limit)
        await interaction.response.defer()
        try:
            await self._original_msg.edit(content="✅ Channel configured!", view=None)
        except discord.HTTPException:
            pass


# ---------------------------------------------------------------------------
# GIM role select
# ---------------------------------------------------------------------------


class GIMRoleSelect(discord.ui.Select):
    """Select menu to choose a GIM team when the member has multiple GIM roles."""

    def __init__(
        self,
        service: TempVCService,
        channel_id: int,
        gim_roles: list[discord.Role],
    ) -> None:
        options = [
            discord.SelectOption(label=role.name, value=str(role.id))
            for role in gim_roles
        ]
        super().__init__(
            placeholder="Select your GIM team…",
            min_values=1,
            max_values=1,
            options=options,
        )
        self._service = service
        self._channel_id = channel_id
        self._role_map = {str(role.id): role.name for role in gim_roles}

    async def callback(self, interaction: discord.Interaction) -> None:
        role_name = self._role_map[self.values[0]]
        logger.debug(f"TempVC: GIM role selected — {role_name!r}")
        await self._service.gim_channel(self._channel_id, role_name)
        await interaction.response.edit_message(
            content=f"✅ Channel renamed to **{role_name}**.", view=None
        )


class GIMRoleSelectView(discord.ui.View):
    def __init__(
        self,
        service: TempVCService,
        channel_id: int,
        gim_roles: list[discord.Role],
    ) -> None:
        super().__init__(timeout=60)
        self.add_item(
            GIMRoleSelect(service=service, channel_id=channel_id, gim_roles=gim_roles)
        )


# ---------------------------------------------------------------------------
# DM view shown after channel creation
# ---------------------------------------------------------------------------


class TempVCDMView(discord.ui.View):
    """Sent as a DM after the temp VC is created, letting the member customise it."""

    def __init__(
        self,
        service: TempVCService,
        channel_id: int,
        gim_roles: list[discord.Role],
    ) -> None:
        super().__init__(timeout=120)
        self._service = service
        self._channel_id = channel_id
        self._gim_roles = gim_roles

    # ------------------------------------------------------------------
    # Auto — keep the channel as-is
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
    # Configure — rename / set user limit via modal
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
    # GIM Channel — rename to a GIM role
    # ------------------------------------------------------------------

    @discord.ui.button(label="GIM Channel", style=discord.ButtonStyle.gray)
    async def gim_channel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not self._gim_roles:
            await interaction.response.send_message(
                "❌ You don't have any configured GIM roles.", ephemeral=True
            )
            return

        if len(self._gim_roles) == 1:
            role_name = self._gim_roles[0].name
            await self._service.gim_channel(self._channel_id, role_name)
            await interaction.response.edit_message(
                content=f"✅ Channel renamed to **{role_name}**.", view=None
            )
        else:
            view = GIMRoleSelectView(
                service=self._service,
                channel_id=self._channel_id,
                gim_roles=self._gim_roles,
            )
            await interaction.response.edit_message(
                content="Select your GIM team:", view=view
            )
        self.stop()


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

        gim_roles = service.get_gim_roles(member)
        logger.debug(
            f"TempVC: sending DM to {member.display_name}"
            f" with {len(gim_roles)} GIM role(s)"
        )
        view = TempVCDMView(service=service, channel_id=channel.id, gim_roles=gim_roles)
        try:
            await member.send(
                "🎤 **Your voice channel has been created!**\n"
                "Choose how you'd like to set it up:",
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
