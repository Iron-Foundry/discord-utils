"""One Lavalink node per player bot, kept for as long as that bot is leased.

Nodes are cached per bot rather than shared, because a player must be built
against the node belonging to the client that connected it. Sharing one node
across bots is what would silently hand a player to the wrong gateway.
"""

from __future__ import annotations

import discord
import wavelink

from music.nodes import close_node, connect_node


class NodeCache:
    """The nodes this process has open, keyed by the bot that owns them."""

    def __init__(self, uri: str, password: str) -> None:
        self._uri = uri
        self._password = password
        self._nodes: dict[int, wavelink.Node] = {}

    async def get(self, bot_index: int, client: discord.Client) -> wavelink.Node:
        node = self._nodes.get(bot_index)
        if node is None:
            node = await connect_node(client, bot_index, self._uri, self._password)
            self._nodes[bot_index] = node
        return node

    async def drop(self, bot_index: int) -> None:
        """Close the node belonging to a bot that is going back into the pool."""
        node = self._nodes.pop(bot_index, None)
        if node is not None:
            await close_node(node)
