"""The two button classes every music control is built from.

Buttons are built imperatively rather than with the decorator form, because
each one needs its session bound to it and the rows are rebuilt on every render
anyway.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import discord

from music.views.context import PanelContext

Action = Callable[[discord.Interaction], Awaitable[None]]


class CallbackButton(discord.ui.Button[Any]):
    """A button whose behaviour is injected rather than subclassed per control."""

    def __init__(self, action: Action, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._action = action

    async def callback(self, interaction: discord.Interaction) -> None:
        await self._action(interaction)


class GuardedButton(CallbackButton):
    """A button that refuses anyone who is not in the voice channel."""

    def __init__(self, context: PanelContext, action: Action, **kwargs: Any) -> None:
        super().__init__(action, **kwargs)
        self._context = context

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await self._context.allows(interaction):
            return
        await self._action(interaction)
