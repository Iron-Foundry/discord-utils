"""Narrowing helper for valkey-py responses.

valkey-py gives the sync and async clients one shared signature, so a command
that returns a concrete type is annotated ``Awaitable[T] | T`` (for example
``hgetall`` is ``Awaitable[dict] | dict``). On the async client it is always the
awaitable branch, but the union still has to be narrowed or the type checker
rejects the ``await``. Commands annotated ``Awaitable[Any] | Any`` need no help,
which is why the rest of the codebase has not hit this.
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Any


async def resolve[T](value: Awaitable[T] | T) -> T:
    """Await a valkey response whose annotation carries a non-awaitable branch."""
    if isinstance(value, Awaitable):
        return await value
    return value


def as_text(value: Any) -> Any:
    """Decode a valkey scalar, which is bytes unless the client decodes responses."""
    return value.decode() if isinstance(value, bytes) else value


def decode_mapping(raw: dict[Any, Any]) -> dict[str, str]:
    """Decode a hash reply into plain strings."""
    return {as_text(key): as_text(value) for key, value in raw.items()}
