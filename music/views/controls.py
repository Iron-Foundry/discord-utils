"""The panel's control rows.

Every callback runs the in-channel check before it touches playback, which is
what `GuardedButton` is for.
"""

from __future__ import annotations

from typing import Any

import discord

from music.models import LoopMode
from music.views.buttons import GuardedButton
from music.views.context import PanelContext
from music.views.snapshot import PanelSnapshot

VOLUME_STEP = 10

NEXT_LOOP = {
    LoopMode.OFF: LoopMode.TRACK,
    LoopMode.TRACK: LoopMode.QUEUE,
    LoopMode.QUEUE: LoopMode.OFF,
}


def transport_row(
    context: PanelContext, snapshot: PanelSnapshot
) -> discord.ui.ActionRow[Any]:
    """What moves the playhead: pause/resume, skip, stop, seek."""
    from music.views.modals import SeekModal

    session = context.session

    async def toggle_pause(interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await session.pause(interaction.user.id, not snapshot.paused)

    async def skip(interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await session.skip(interaction.user.id)

    async def stop(interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await session.stop(interaction.user.id)

    async def seek(interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(SeekModal(context))

    idle = snapshot.is_idle
    seekable = not idle and not (
        snapshot.current is not None and snapshot.current.is_stream
    )
    return discord.ui.ActionRow(
        GuardedButton(
            context,
            toggle_pause,
            emoji="▶️" if snapshot.paused else "⏸️",
            style=discord.ButtonStyle.primary,
            disabled=idle,
        ),
        GuardedButton(context, skip, emoji="⏭️", disabled=idle),
        GuardedButton(
            context, stop, emoji="⏹️", style=discord.ButtonStyle.danger, disabled=idle
        ),
        GuardedButton(context, seek, emoji="⏩", disabled=not seekable),
    )


def modifier_row(
    context: PanelContext, snapshot: PanelSnapshot
) -> discord.ui.ActionRow[Any]:
    """What changes how it plays rather than what plays: volume, loop, shuffle."""
    session = context.session

    async def volume_down(interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await session.set_volume(interaction.user.id, snapshot.volume - VOLUME_STEP)

    async def volume_up(interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await session.set_volume(interaction.user.id, snapshot.volume + VOLUME_STEP)

    async def cycle_loop(interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await session.set_loop(interaction.user.id, NEXT_LOOP[snapshot.loop])

    async def toggle_shuffle(interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await session.set_shuffle(interaction.user.id, not snapshot.shuffle)

    return discord.ui.ActionRow(
        GuardedButton(context, volume_down, emoji="🔉", disabled=snapshot.volume <= 0),
        GuardedButton(context, volume_up, emoji="🔊"),
        GuardedButton(
            context,
            cycle_loop,
            label=_loop_label(snapshot.loop),
            style=_loop_style(snapshot.loop),
        ),
        GuardedButton(
            context,
            toggle_shuffle,
            emoji="🔀",
            style=_toggle_style(snapshot.shuffle),
        ),
    )


def views_row(context: PanelContext) -> discord.ui.ActionRow[Any]:
    """The ephemeral views. Each opens per viewer, never on the panel."""
    # Imported here rather than at module scope: every view builds buttons from
    # this module, so a top-level import would close the cycle.
    from music.views.activity_view import send_activity
    from music.views.history_view import send_history
    from music.views.playlist_view import send_playlists
    from music.views.queue_view import send_queue

    async def queue(interaction: discord.Interaction) -> None:
        await send_queue(interaction, context)

    async def history(interaction: discord.Interaction) -> None:
        await send_history(interaction, context)

    async def activity(interaction: discord.Interaction) -> None:
        await send_activity(interaction, context)

    async def playlists(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        await send_playlists(interaction, context)

    buttons = [
        GuardedButton(context, queue, label="Queue"),
        GuardedButton(context, history, label="History"),
        GuardedButton(context, activity, label="Activity"),
    ]
    # No playlist API configured means no button at all, rather than one that
    # errors when it is pressed.
    if context.playlists is not None:
        buttons.append(GuardedButton(context, playlists, label="Playlists"))
    return discord.ui.ActionRow(*buttons)


def _loop_label(mode: LoopMode) -> str:
    return {
        LoopMode.OFF: "🔁 Off",
        LoopMode.TRACK: "🔂 Track",
        LoopMode.QUEUE: "🔁 All",
    }[mode]


def _loop_style(mode: LoopMode) -> discord.ButtonStyle:
    return _toggle_style(mode is not LoopMode.OFF)


def _toggle_style(enabled: bool) -> discord.ButtonStyle:
    """Lit while a mode is in force, so the row shows its own state."""
    return discord.ButtonStyle.success if enabled else discord.ButtonStyle.secondary
