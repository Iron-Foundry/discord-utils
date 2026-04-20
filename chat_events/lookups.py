"""Boss, skill, and clue lookup tables loaded from TOML data files."""

from __future__ import annotations

import tomllib
from pathlib import Path

_DATA_DIR = Path(__file__).parent / "data"

_WOM_SECTION_KEY = "wom_section"


def _load_skills() -> dict[str, str]:
    with (_DATA_DIR / "skills.toml").open("rb") as f:
        raw = tomllib.load(f)
    mapping: dict[str, str] = {}
    for section_key, entry in raw.items():
        wom_key: str = entry.get("wom_key", section_key)
        mapping[section_key.lower()] = wom_key
        for alias in entry.get("aliases", []):
            mapping[alias.lower().strip()] = wom_key
    return mapping


def _load_bosses() -> tuple[dict[str, tuple[str, str, str]],]:
    """Return alias → (wom_key, display, wom_section) mapping."""
    with (_DATA_DIR / "bosses.toml").open("rb") as f:
        raw = tomllib.load(f)
    mapping: dict[str, tuple[str, str, str]] = {}
    for section_key, entry in raw.items():
        wom_key: str = entry.get("wom_key", section_key)
        display: str = entry.get("display", section_key.replace("_", " ").title())
        wom_section: str = entry.get(_WOM_SECTION_KEY, "bosses")
        value = (wom_key, display, wom_section)
        mapping[section_key.lower()] = value
        for alias in entry.get("aliases", []):
            mapping[alias.lower().strip()] = value
    return (mapping,)


_SKILL_ALIASES: dict[str, str] = _load_skills()
(_BOSS_ALIASES,) = _load_bosses()

_CLUE_TIERS: dict[str, str] = {
    "total": "clue_scrolls_all",
    "all": "clue_scrolls_all",
    "beginner": "clue_scrolls_beginner",
    "easy": "clue_scrolls_easy",
    "medium": "clue_scrolls_medium",
    "hard": "clue_scrolls_hard",
    "elite": "clue_scrolls_elite",
    "master": "clue_scrolls_master",
}

_CLUE_DISPLAY: dict[str, str] = {
    "clue_scrolls_all": "Total Clues",
    "clue_scrolls_beginner": "Beginner Clues",
    "clue_scrolls_easy": "Easy Clues",
    "clue_scrolls_medium": "Medium Clues",
    "clue_scrolls_hard": "Hard Clues",
    "clue_scrolls_elite": "Elite Clues",
    "clue_scrolls_master": "Master Clues",
}

_CLUE_TIER_ORDER = [
    "clue_scrolls_beginner",
    "clue_scrolls_easy",
    "clue_scrolls_medium",
    "clue_scrolls_hard",
    "clue_scrolls_elite",
    "clue_scrolls_master",
]


def resolve_boss(query: str) -> tuple[str, str, str] | None:
    """Return (wom_key, display_name, wom_section) for a boss query, or None.

    wom_section is either "bosses" or "activities".
    """
    return _BOSS_ALIASES.get(query.lower().strip())


def resolve_skill(query: str) -> str | None:
    """Return the WOM skill key for a query, or None."""
    return _SKILL_ALIASES.get(query.lower().strip())


def resolve_clue_tier(query: str) -> tuple[str, str] | None:
    """Return (wom_key, display_name) for a clue tier query, or None."""
    wom_key = _CLUE_TIERS.get(query.lower().strip())
    if wom_key is None:
        return None
    return wom_key, _CLUE_DISPLAY[wom_key]


def all_clue_tiers() -> list[tuple[str, str]]:
    """Return ordered list of (wom_key, display_name) for all individual tiers."""
    return [(k, _CLUE_DISPLAY[k]) for k in _CLUE_TIER_ORDER]
