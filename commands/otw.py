from __future__ import annotations

import io
from typing import Optional

import discord
from discord import app_commands
from loguru import logger

from imagegen.canvas import OTWCanvas
from imagegen.fonts import FontSet
from imagegen.icons import BossIcon, SkillIcon
from imagegen.layouts import DOUBLE_LAYOUT, SINGLE_LAYOUT, TRIPLE_LAYOUT
from imagegen.models import CanvasLayout, ColorKey, OTWEntry

LAYOUT = CanvasLayout(
    constrain_left=91,
    constrain_right=1312,
    constrain_top=60,
    constrain_bottom=712,
    pad_x=60,
    pad_y=60,
)
LAYOUT.colors = (ColorKey.SOTW, (57, 117, 64))
LAYOUT.colors = (ColorKey.BOTW, (45, 72, 247))
LAYOUT.colors = (ColorKey.ROTW, (110, 7, 245))
LAYOUT.colors = (ColorKey.HIGHLIGHT_DATE, (128, 0, 32))

FONTS = FontSet(
    bold_path="assets/fonts/RuneScape-Bold-12.otf",
    quill_path="assets/fonts/RuneScape-Quill.otf",
)

ALL_SKILLS = [
    app_commands.Choice(name=icon.name.replace("_", " ").title(), value=icon.name)
    for icon in SkillIcon
]

ALL_BOSSES = [
    app_commands.Choice(name=icon.name.replace("_", " ").title(), value=icon.name)
    for icon in BossIcon
]

RAID_DISPLAY_NAMES: dict[str, str] = {
    "COX": "Chambers of Xeric",
    "TOB": "Theatre of Blood",
    "TOA": "Tombs of Amascut",
}

ALL_RAIDS = [
    app_commands.Choice(name=name, value=value)
    for value, name in RAID_DISPLAY_NAMES.items()
]

_PRESET_MAP = {
    1: SINGLE_LAYOUT,
    2: DOUBLE_LAYOUT,
    3: TRIPLE_LAYOUT,
}


def _filter_choices(
    choices: list[app_commands.Choice[str]], current: str
) -> list[app_commands.Choice[str]]:
    if not current:
        return choices[:25]
    lower = current.lower()
    return [c for c in choices if lower in c.name.lower()][:25]


async def skill_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    return _filter_choices(ALL_SKILLS, current)


async def boss_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    return _filter_choices(ALL_BOSSES, current)


async def raid_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    return _filter_choices(ALL_RAIDS, current)


def _resolve_entry(
    value: Optional[str],
    label: str,
    icon_enum: type[BossIcon] | type[SkillIcon],
    color_key: ColorKey,
    display_names: Optional[dict[str, str]] = None,
) -> Optional[OTWEntry]:
    """Resolve a raw autocomplete value into an OTWEntry, or None if not provided."""
    if not value:
        return None
    try:
        icon = icon_enum[value]
    except KeyError:
        return None
    name = (
        display_names[value]
        if display_names and value in display_names
        else value.replace("_", " ").title()
    )
    return OTWEntry(
        label=label,
        name=name,
        icon_path=icon.path,
        color_key=color_key,
    )


def make_otw_command() -> app_commands.Command:  # type: ignore[type-arg]
    """Return a ready-to-add /otw slash command."""

    @app_commands.command(name="otw", description="Generate an Of The Week image")
    @app_commands.describe(
        date="Date range (e.g. 'March 3–10')",
        skill="Skill of the week",
        boss="Boss of the week",
        raid="Raid of the week",
    )
    @app_commands.autocomplete(
        skill=skill_autocomplete,
        boss=boss_autocomplete,
        raid=raid_autocomplete,
    )
    @app_commands.default_permissions(manage_guild=True)
    async def otw(
        interaction: discord.Interaction,
        date: str,
        skill: Optional[str] = None,
        boss: Optional[str] = None,
        raid: Optional[str] = None,
    ) -> None:
        logger.debug(f"OTW: invoked by {interaction.user}, date={date!r}")
        await interaction.response.defer()

        entry_configs = [
            (skill, "SKILL OF THE WEEK", SkillIcon, ColorKey.SOTW, None),
            (boss, "BOSS OF THE WEEK", BossIcon, ColorKey.BOTW, None),
            (raid, "RAID OF THE WEEK", BossIcon, ColorKey.ROTW, RAID_DISPLAY_NAMES),
        ]

        entries: list[OTWEntry] = []
        for value, label, icon_enum, color_key, names in entry_configs:
            entry = _resolve_entry(value, label, icon_enum, color_key, names)
            if value and not entry:
                await interaction.followup.send(
                    f"Unknown value: {value!r}", ephemeral=True
                )
                return
            if entry:
                entries.append(entry)

        if not entries:
            await interaction.followup.send(
                "You must select at least one skill, boss, or raid.",
                ephemeral=True,
            )
            return

        preset = _PRESET_MAP.get(len(entries))
        if not preset:
            await interaction.followup.send(
                "Invalid number of entries.", ephemeral=True
            )
            return

        canvas = OTWCanvas(
            base_path="assets/backgrounds/otw_base.png",
            layout=LAYOUT,
            fonts=FONTS,
            preset=preset,
            date_text=date,
        )
        image = canvas.render(entries)

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        buf.seek(0)

        await interaction.followup.send(file=discord.File(buf, filename="otw.png"))

    return otw  # type: ignore[return-value]
