"""Clan stats command — shows CC rank distribution as a Plotly bar chart."""

from __future__ import annotations

import asyncio
import io

import discord
import plotly.graph_objects as go
from discord import app_commands
from loguru import logger

from commands.checks import handle_check_failure, is_staff
from commands.help_registry import HelpEntry, HelpGroup, HelpRegistry

_BG = "#313338"
_GRID = "#383a40"
_TEXT = "#dbdee1"

_RANKS: list[tuple[str, str]] = [
    ("Sapphire", "#1D7CE1"),
    ("Emerald", "#00A550"),
    ("Ruby", "#CE1126"),
    ("Diamond", "#B9F2FF"),
    ("Dragonstone", "#00BFBF"),
    ("Onyx", "#4A4A4A"),
    ("Zenyte", "#F5A623"),
]

_RANK_NAMES = [name for name, _ in _RANKS]
_RANK_COLORS = [color for _, color in _RANKS]


def _compute_median_rank(rank_names: list[str], counts: list[int]) -> str:
    """Return the rank tier containing the 50th-percentile member."""
    total = sum(counts)
    if total == 0:
        return "N/A"
    target = total / 2
    cumulative = 0
    for name, count in zip(rank_names, counts):
        cumulative += count
        if cumulative >= target:
            return name
    return rank_names[-1]


async def _build_chart(
    rank_names: list[str],
    counts: list[int],
    colors: list[str],
) -> discord.File | None:
    """Render a vertical bar chart of CC rank distribution.

    Returns None if rendering fails.
    """
    fig = go.Figure(
        go.Bar(
            x=rank_names,
            y=counts,
            marker_color=colors,
            text=counts,
            textposition="outside",
            textfont={"color": _TEXT},
        )
    )
    fig.update_layout(  # type: ignore[call-arg]
        paper_bgcolor=_BG,
        plot_bgcolor=_BG,
        font={"color": _TEXT, "family": "Arial, sans-serif"},
        margin={"l": 60, "r": 30, "t": 50, "b": 60},
        title={"text": "CC Rank Distribution", "font": {"color": _TEXT}},
        xaxis={"gridcolor": _GRID, "zerolinecolor": _GRID},
        yaxis={"gridcolor": _GRID, "zerolinecolor": _GRID},
    )
    try:
        img_bytes: bytes = await asyncio.to_thread(
            fig.to_image, format="png", width=700, height=400
        )
        return discord.File(io.BytesIO(img_bytes), filename="clan_stats.png")
    except Exception as e:
        logger.warning(f"Failed to render clan stats chart: {e}")
        return None


def _gather_counts(guild: discord.Guild) -> tuple[list[int], list[str]]:
    """Return per-rank member counts and names of any missing roles."""
    role_map = {role.name: role for role in guild.roles}
    counts: list[int] = []
    missing: list[str] = []
    for name, _ in _RANKS:
        role = role_map.get(name)
        if role is None:
            counts.append(0)
            missing.append(name)
        else:
            counts.append(len(role.members))
    return counts, missing


def _build_embed(
    rank_names: list[str],
    counts: list[int],
    missing: list[str],
) -> discord.Embed:
    """Build the stats embed for the clan rank distribution."""
    total = sum(counts)
    embed = discord.Embed(
        title="CC Rank Distribution",
        color=discord.Color.blurple(),
    )
    embed.add_field(name="Total ranked members", value=str(total), inline=False)

    lines: list[str] = []
    for name, count in zip(rank_names, counts):
        pct = f"{count / total * 100:.1f}%" if total > 0 else "0.0%"
        lines.append(f"**{name}:** {count} ({pct})")
    embed.add_field(name="Per-rank breakdown", value="\n".join(lines), inline=False)

    median = _compute_median_rank(rank_names, counts)
    embed.add_field(name="Median rank", value=median, inline=True)

    if total > 0:
        most_common_idx = counts.index(max(counts))
        embed.add_field(
            name="Most common rank", value=rank_names[most_common_idx], inline=True
        )
        nonzero = [c for c in counts if c > 0]
        if nonzero:
            rarest_idx = counts.index(min(nonzero))
            embed.add_field(
                name="Rarest rank", value=rank_names[rarest_idx], inline=True
            )

    if missing:
        embed.set_footer(
            text=f"Roles not found in guild (shown as 0): {', '.join(missing)}"
        )

    embed.set_image(url="attachment://clan_stats.png")
    return embed


def make_clan_stats_command() -> app_commands.Command:  # type: ignore[type-arg]
    """Return a ready-to-add /clanstats slash command."""

    @app_commands.command(
        name="clanstats", description="Show CC rank member distribution"
    )
    @is_staff()
    async def clanstats(interaction: discord.Interaction) -> None:
        logger.debug(f"clanstats: invoked by {interaction.user}")
        await interaction.response.defer(thinking=True)

        guild = interaction.guild
        if guild is None:
            await interaction.followup.send(
                "This command must be used in a server.", ephemeral=True
            )
            return

        counts, missing = _gather_counts(guild)
        chart = await _build_chart(_RANK_NAMES, counts, _RANK_COLORS)
        embed = _build_embed(_RANK_NAMES, counts, missing)

        if chart is None:
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(embed=embed, file=chart)

    @clanstats.error
    async def clanstats_error(
        interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        await handle_check_failure(interaction, error)

    return clanstats  # type: ignore[return-value]


def register_help(registry: HelpRegistry) -> None:
    """Register /clanstats in the help registry."""
    registry.add_group(
        HelpGroup(
            name="clanstats",
            description="Clan rank statistics and member distribution",
            commands=[
                HelpEntry(
                    "/clanstats",
                    "Show CC rank member distribution chart",
                    "Staff",
                ),
            ],
        )
    )
