"""The panel: one Components V2 message per session.

This message is components-v2 only, on send and on every edit. The flag cannot
be removed from a message once it has been sent, and `content` and `embeds`
stop working under it, so nothing here may ever pass either.
"""

from __future__ import annotations

from typing import Any

import discord

from music.views.context import PanelContext
from music.views.controls import modifier_row, transport_row, views_row
from music.views.format import accent_colour, now_playing, status_line, up_next
from music.views.selects import jump_row
from music.views.snapshot import PanelSnapshot

# The API caps a message at 40 components and 4000 display characters. The
# panel is nowhere near either, and a test asserts it stays that way.
MAX_COMPONENTS = 40
MAX_CHARACTERS = 4000


class MusicPanel(discord.ui.LayoutView):
    """The live controls for one voice channel."""

    def __init__(self, context: PanelContext, snapshot: PanelSnapshot) -> None:
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Container(
                *_body(context, snapshot),
                accent_colour=accent_colour(snapshot),
            )
        )


def _body(context: PanelContext, snapshot: PanelSnapshot) -> list[discord.ui.Item[Any]]:
    items: list[discord.ui.Item[Any]] = [_header(snapshot)]
    items.append(discord.ui.Separator())
    items.append(discord.ui.TextDisplay(up_next(snapshot)))
    items.append(discord.ui.TextDisplay(status_line(snapshot)))
    items.append(transport_row(context, snapshot))
    items.append(modifier_row(context, snapshot))
    items.append(views_row(context))

    jump = jump_row(context, snapshot)
    if jump is not None:
        items.append(jump)
    return items


def _header(snapshot: PanelSnapshot) -> discord.ui.Item[Any]:
    """The now-playing block, with artwork as the section accessory when there is any."""
    text = discord.ui.TextDisplay(now_playing(snapshot))
    artwork = snapshot.current.artwork if snapshot.current else None
    if not artwork:
        return text
    return discord.ui.Section(text, accessory=discord.ui.Thumbnail(artwork))
