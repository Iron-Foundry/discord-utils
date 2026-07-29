"""Registers the music commands and their help entries.

The commands are flat rather than a `/music` group: they are typed constantly
and by everyone, so an extra word in front of each one is friction with nothing
to show for it.
"""

from __future__ import annotations

from typing import Any

import discord
from discord import app_commands
from loguru import logger

from command_infra.help_registry import HelpEntry, HelpGroup, HelpRegistry
from music.commands.playback import (
    make_pause_command,
    make_play_command,
    make_resume_command,
    make_seek_command,
    make_skip_command,
    make_stop_command,
)
from music.commands.playlists import make_playlist_command
from music.commands.queueing import (
    make_loop_command,
    make_nowplaying_command,
    make_queue_command,
    make_remove_command,
    make_shuffle_command,
    make_volume_command,
)
from music.service import MusicService

# Everyone in the voice channel controls it, so there is no staff tier here.
ACCESS = "Member"

HELP_ENTRIES = [
    ("/play <query> [source]", "Queue a track, playlist or link"),
    ("/pause", "Pause playback"),
    ("/resume", "Resume playback"),
    ("/skip", "Skip the current track"),
    ("/stop", "Stop playback and clear the queue"),
    ("/seek <mm:ss>", "Jump to a position in the current track"),
    ("/queue", "Show the queue, and remove or move tracks"),
    ("/nowplaying", "Show what is playing and what is next"),
    ("/remove <position>", "Remove one track from the queue"),
    ("/shuffle", "Shuffle the queue"),
    ("/loop <mode>", "Repeat nothing, the track, or the queue"),
    ("/volume <percent>", "Set the volume"),
    ("/playlist", "Load one of your saved playlists"),
]


def build_commands(service: MusicService) -> list[app_commands.Command[Any, Any, Any]]:
    """Every music command, bound to the running service."""
    return [
        make_play_command(service),
        make_pause_command(service),
        make_resume_command(service),
        make_skip_command(service),
        make_stop_command(service),
        make_seek_command(service),
        make_queue_command(service),
        make_nowplaying_command(service),
        make_remove_command(service),
        make_shuffle_command(service),
        make_loop_command(service),
        make_volume_command(service),
        make_playlist_command(service),
    ]


def register_help(registry: HelpRegistry) -> None:
    """Register the music help group."""
    registry.add_group(
        HelpGroup(
            name="music",
            description="Play music in your voice channel",
            commands=[
                HelpEntry(name, description, ACCESS)
                for name, description in HELP_ENTRIES
            ],
        )
    )


def register(
    service: MusicService,
    tree: app_commands.CommandTree,
    guild: discord.Guild,
    registry: HelpRegistry,
) -> None:
    """Add every music command to the tree and list them in /help."""
    commands = build_commands(service)
    for command in commands:
        tree.add_command(command, guild=guild)
    register_help(registry)
    logger.info("Music: {} slash commands registered", len(commands))
