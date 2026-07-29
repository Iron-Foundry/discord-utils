"""Reading saved playlists from api-backend.

discord-utils holds no user JWT - nobody completes an OAuth flow to press a
panel button - so it reads through the service-key surface, naming the Discord
user it is acting for. That surface is read-only by design: creating and
editing playlists stays behind a real login on the web, so the shared key can
never write on someone's behalf.
"""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger
from pydantic import BaseModel

from music.models import Track

REQUEST_TIMEOUT_SECONDS = 10.0
# Discord caps a select at 25 options, so that is as many as can be offered.
PLAYLISTS_SHOWN = 25

UNREACHABLE = "The playlist service is not reachable right now."
MISSING = "That playlist no longer exists, or is not shared with you."
REFUSED = "The playlist service refused that request."


class PlaylistError(RuntimeError):
    """A playlist could not be read. Carries a message fit to show a user."""


class SavedTrack(BaseModel):
    """One track as api-backend stores it: metadata, never audio."""

    source: str
    identifier: str
    title: str
    author: str
    duration_ms: int
    isrc: str | None = None
    uri: str | None = None
    artwork: str | None = None
    position: int = 0


class PlaylistSummary(BaseModel):
    """A playlist as it appears in a list, without its tracks."""

    id: int
    owner_discord_id: int
    name: str
    is_public: bool
    track_count: int


class PlaylistDetail(PlaylistSummary):
    """A playlist with everything needed to queue it."""

    tracks: list[SavedTrack] = []


class PlaylistClient:
    """The read half of `/music/bot/{discord_user_id}/playlists`."""

    def __init__(
        self,
        base_url: str,
        service_key: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {"verification-code": service_key}
        # httpx's own seam for testing. None is what a plain client uses.
        self._transport = transport

    async def for_user(self, discord_user_id: int) -> list[PlaylistSummary]:
        """Playlists this user may load: their own, plus every public one."""
        payload = await self._get(f"/music/bot/{discord_user_id}/playlists")
        return [PlaylistSummary.model_validate(row) for row in payload]

    async def detail(self, discord_user_id: int, playlist_id: int) -> PlaylistDetail:
        """One playlist with its tracks, if this user is allowed to see it."""
        payload = await self._get(
            f"/music/bot/{discord_user_id}/playlists/{playlist_id}"
        )
        return PlaylistDetail.model_validate(payload)

    async def _get(self, path: str) -> Any:
        try:
            async with httpx.AsyncClient(
                timeout=REQUEST_TIMEOUT_SECONDS, transport=self._transport
            ) as http:
                response = await http.get(self._base_url + path, headers=self._headers)
        except httpx.HTTPError as exc:
            logger.warning("Music: playlist request to {} failed: {}", path, exc)
            raise PlaylistError(UNREACHABLE) from exc

        # A playlist the caller may not see answers 404 rather than 403, so
        # "gone" and "not yours" are deliberately the same message here too.
        if response.status_code == 404:
            raise PlaylistError(MISSING)
        if response.status_code >= 400:
            logger.warning(
                "Music: playlist request to {} returned HTTP {}",
                path,
                response.status_code,
            )
            raise PlaylistError(REFUSED)
        return response.json()


def to_track(row: SavedTrack, *, requester_id: int) -> Track:
    """One saved row as a queueable track.

    A saved track carries metadata and no Lavalink audio, so it is queued
    unresolved and the audio is looked up only when it reaches the front of the
    queue. A two hundred track playlist therefore loads in one request instead
    of two hundred searches, and a track nobody ever hears costs nothing.
    """
    return Track(
        identifier=row.identifier,
        title=row.title,
        author=row.author,
        length_ms=row.duration_ms,
        is_stream=False,
        uri=row.uri,
        artwork=row.artwork,
        isrc=row.isrc,
        source=row.source,
        requested_source=row.source,
        requester_id=requester_id,
    )


def to_tracks(playlist: PlaylistDetail, *, requester_id: int) -> list[Track]:
    """Saved rows as queueable tracks, in the order they were saved."""
    return [
        to_track(row, requester_id=requester_id)
        for row in sorted(playlist.tracks, key=lambda row: row.position)
    ]
