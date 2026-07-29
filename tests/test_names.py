"""Nickname list invariants. No Valkey, no Discord."""

from __future__ import annotations

import pytest

from music.names import NICKNAME_LIMIT, combinations, load_words


def test_lists_load_and_are_non_empty() -> None:
    osrs, music = load_words()
    assert osrs and music


def test_every_pair_fits_the_discord_nickname_limit() -> None:
    osrs, music = load_words()
    longest = max(
        (f"{a} {b}" for a in osrs for b in music),
        key=len,
    )
    assert len(longest) <= NICKNAME_LIMIT, longest


def test_words_are_single_tokens() -> None:
    osrs, music = load_words()
    offenders = [word for word in (*osrs, *music) if " " in word or not word.isalpha()]
    assert offenders == []


def test_no_duplicates_within_either_list() -> None:
    osrs, music = load_words()
    assert len(set(osrs)) == len(osrs)
    assert len(set(music)) == len(music)


def test_combinations_matches_the_lists() -> None:
    osrs, music = load_words()
    assert combinations() == len(osrs) * len(music)


@pytest.mark.parametrize("expected_minimum", [1000])
def test_pool_is_large_enough_to_avoid_constant_collisions(
    expected_minimum: int,
) -> None:
    # Five concurrent bots draw from this space; a small space would make the
    # bounded retry loop in roll_nickname fail on unlucky draws.
    assert combinations() >= expected_minimum
