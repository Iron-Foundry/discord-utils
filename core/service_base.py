"""Abstract base class that every bot service must implement."""

from __future__ import annotations

from abc import ABC, abstractmethod

import discord


class Service(ABC):
    """Base class for all bot services.

    Provides a concrete ``guild`` property backed by ``_guild``, so subclasses
    only need to set ``self._guild`` in their ``__init__``.  The two lifecycle
    hooks - ``initialize`` and ``post_ready`` - define the contract the
    :class:`ServiceHandler` relies on.
    """

    _guild: discord.Guild

    @property
    def guild(self) -> discord.Guild:
        """The guild this service is bound to."""
        return self._guild

    @guild.setter
    def guild(self, guild: discord.Guild) -> None:
        self._guild = guild

    @abstractmethod
    async def initialize(self) -> None:
        """Called during ``setup_hook`` to initialise the service."""

    async def post_ready(self) -> None:
        """Called after ``on_ready`` with the live guild cache.

        Override when the service needs the fully-populated gateway guild
        (e.g. to re-attach to existing channels or messages).  No-op by default.
        """
