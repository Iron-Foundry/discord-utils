"""Pool logic that needs neither Valkey nor Discord."""

from __future__ import annotations

import pytest

from music.models import PoolExhaustedError, PoolSlot
from music.pool import MAX_BOTS, BotPool
from music.service import parse_tokens


def test_parse_tokens_splits_and_trims() -> None:
    assert parse_tokens(" a , b ,c ") == ["a", "b", "c"]


def test_parse_tokens_treats_blank_as_disabled() -> None:
    assert parse_tokens(None) == []
    assert parse_tokens("") == []
    assert parse_tokens("  ,  ,") == []


def test_parse_tokens_caps_at_the_pool_maximum() -> None:
    assert len(parse_tokens(",".join(str(i) for i in range(9)))) == MAX_BOTS


def test_pool_rejects_more_tokens_than_slots() -> None:
    with pytest.raises(ValueError, match="At most 5"):
        BotPool([str(i) for i in range(MAX_BOTS + 1)], valkey=None)  # type: ignore[arg-type]


def test_pool_slot_free_state() -> None:
    assert PoolSlot(bot_index=0).is_free
    assert not PoolSlot(bot_index=0, voice_channel_id=42).is_free


def test_pool_exhausted_names_the_occupied_channels() -> None:
    error = PoolExhaustedError(
        [
            PoolSlot(bot_index=0, voice_channel_id=11),
            PoolSlot(bot_index=1, voice_channel_id=22),
        ]
    )
    assert "<#11>" in str(error)
    assert "<#22>" in str(error)
