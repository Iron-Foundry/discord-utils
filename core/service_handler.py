"""Manages the shared lifecycle of all registered services."""

from __future__ import annotations

from typing import TypeVar

import discord
from loguru import logger

from core.service_base import Service

S = TypeVar("S", bound=Service)


class ServiceHandler:
    """Owns the list of active services and drives their lifecycle hooks.

    The client delegates guild-refresh and post-ready calls here so that
    adding a new service requires no changes to :class:`DiscordClient`.
    """

    def __init__(self) -> None:
        self._services: list[Service] = []

    def register(self, *services: Service) -> None:
        """Register one or more services with the handler."""
        self._services.extend(services)
        logger.debug(
            f"ServiceHandler: {len(services)} service(s) registered"
            f" ({len(self._services)} total)"
        )

    def refresh_guilds(self, guild: discord.Guild) -> None:
        """Propagate the live gateway guild to all registered services."""
        for service in self._services:
            service.guild = guild
        logger.debug(
            f"ServiceHandler: guild refreshed for {len(self._services)} service(s)"
        )

    async def run_post_ready(self) -> None:
        """Run ``post_ready`` on every service sequentially."""
        for service in self._services:
            await service.post_ready()

    def get(self, service_type: type[S]) -> S | None:
        """Return the first registered service of *service_type*, or ``None``."""
        for service in self._services:
            if isinstance(service, service_type):
                return service
        return None
