"""One Lavalink node per player bot.

All five nodes point at the same Lavalink server. Lavalink keys sessions by a
generated session id and holds the player map per connection, so one server
serves five bot identities without them seeing each other.

The split matters on the client side: `wavelink.Pool` picks a node by player
count and never checks which bot a node belongs to, so anything that lets the
Pool choose can silently drive another bot's player. Every call site therefore
passes its own node explicitly, and players are constructed through
`player_class` rather than by wavelink's default lookup.
"""

from __future__ import annotations

import functools
from collections.abc import Callable

import discord
import wavelink
from loguru import logger

# wavelink fires `wavelink_inactive_player` after this long without playback,
# which is what tears an idle session down. Empty-channel teardown is separate
# and immediate: it reacts to voice state instead of waiting for a track to end.
IDLE_TIMEOUT_SECONDS = 300
EMPTY_CHANNEL_TOKENS = 1


async def connect_node(
    client: discord.Client,
    bot_index: int,
    uri: str,
    password: str,
) -> wavelink.Node:
    """Open this bot's own node against the shared Lavalink server."""
    node = wavelink.Node(
        identifier=f"music-bot-{bot_index}",
        uri=uri,
        password=password,
        client=client,
        inactive_player_timeout=IDLE_TIMEOUT_SECONDS,
        inactive_channel_tokens=EMPTY_CHANNEL_TOKENS,
    )
    await wavelink.Pool.connect(nodes=[node], client=client)
    logger.info("Music: node {} connected for bot {}", node.identifier, bot_index)
    return node


def player_class(
    node: wavelink.Node,
) -> Callable[[discord.Client, discord.abc.Connectable], wavelink.Player]:
    """A Player bound to one node, for passing as `cls=` to `channel.connect`.

    discord.py types `cls` as `Callable[[Client, Connectable], T]` and calls it
    as `cls(client, channel)`, which a partial satisfies. Without the bound
    node, `Player.__init__` falls back to `Pool.get_node()` and can pick a node
    belonging to a different bot.
    """
    return functools.partial(wavelink.Player, nodes=[node])


async def close_node(node: wavelink.Node) -> None:
    """Drop a node and its Pool registration when a bot is released."""
    try:
        await node.close(eject=True)
    except Exception as exc:
        logger.warning("Music: node {} failed to close: {}", node.identifier, exc)
