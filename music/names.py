"""Random two-word session nicknames, unique across the live pool."""

from __future__ import annotations

import secrets
import tomllib
from functools import lru_cache
from pathlib import Path

from valkey.asyncio import Valkey

from music.valkey_io import resolve

NICKNAME_LIMIT = 32
NAMES_KEY = "music:names"
_DATA_FILE = Path(__file__).parent / "data" / "names.toml"
_MAX_DRAWS = 32


class NameRollError(RuntimeError):
    """No unused nickname could be drawn."""


@lru_cache(maxsize=1)
def load_words() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Load and validate the two word lists.

    Asserts that the longest possible pair fits Discord's nickname cap, so a
    word added later can never silently truncate a live bot's name.
    """
    with _DATA_FILE.open("rb") as handle:
        data = tomllib.load(handle)

    osrs: list[str] = data["osrs_words"]
    music: list[str] = data["music_words"]
    if not osrs or not music:
        raise ValueError(f"{_DATA_FILE.name}: both word lists must be non-empty")

    longest = max(map(len, osrs)) + 1 + max(map(len, music))
    if longest > NICKNAME_LIMIT:
        raise ValueError(
            f"{_DATA_FILE.name}: longest pair is {longest} characters,"
            f" over Discord's {NICKNAME_LIMIT} character nickname limit"
        )
    return tuple(osrs), tuple(music)


def combinations() -> int:
    """Total number of distinct nicknames the lists can produce."""
    osrs, music = load_words()
    return len(osrs) * len(music)


async def roll_nickname(valkey: Valkey) -> str:
    """Claim an unused nickname, or raise if the draw keeps colliding.

    Uniqueness is enforced by the Valkey set itself: SADD returns 1 only for a
    name nobody else holds, which makes the claim atomic across concurrent
    leases rather than a check-then-set race.
    """
    osrs, music = load_words()
    for _ in range(_MAX_DRAWS):
        nickname = f"{secrets.choice(osrs)} {secrets.choice(music)}"
        if await resolve(valkey.sadd(NAMES_KEY, nickname)):
            return nickname
    raise NameRollError(f"No free nickname after {_MAX_DRAWS} draws")


async def release_nickname(valkey: Valkey, nickname: str) -> None:
    """Return a nickname to the pool."""
    await resolve(valkey.srem(NAMES_KEY, nickname))
