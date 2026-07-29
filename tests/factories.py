"""Track fixtures shaped exactly like a Lavalink v4 load response."""

from __future__ import annotations

from typing import Any

import wavelink

from music.models import Track


def make_payload(
    *,
    identifier: str = "track-1",
    title: str = "Zanaris Nocturne",
    author: str = "Barbarian Assault",
    length: int = 180_000,
    isrc: str | None = "USABC1234567",
    source: str = "spotify",
) -> dict[str, Any]:
    """A Lavalink track payload. Field names match the v4 API exactly."""
    info: dict[str, Any] = {
        "identifier": identifier,
        "isSeekable": True,
        "author": author,
        "length": length,
        "isStream": False,
        "position": 0,
        "title": title,
        "uri": f"https://example.invalid/{identifier}",
        "artworkUrl": "https://example.invalid/art.png",
        "sourceName": source,
    }
    if isrc is not None:
        info["isrc"] = isrc
    return {
        "encoded": f"encoded-{identifier}",
        "info": info,
        "pluginInfo": {},
        "userData": {},
    }


def make_playable(**kwargs: Any) -> wavelink.Playable:
    return wavelink.Playable(make_payload(**kwargs))  # type: ignore[arg-type]


def make_track(*, requester_id: int = 7, **kwargs: Any) -> Track:
    playable = make_playable(**kwargs)
    return Track.from_playable(
        playable, requested_source=playable.source, requester_id=requester_id
    )
