"""Playback selection policies using an injected Daily Wire client.

No application ORM, API models, settings or scheduler dependencies belong here.
The provider's metadata is returned untouched for the application to persist.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .errors import MediaUnavailableError


class MoviePlaybackClient(Protocol):
    def get_movie_playback(self, slug: str) -> Any: ...
    def get_movie_extra_playback(self, slug: str) -> Any: ...
    def get_movie_page(self, slug: str) -> Any: ...


@dataclass(frozen=True)
class PlaybackSelection:
    url: str
    metadata: Any = None


def resolve_movie_playback(
    client: MoviePlaybackClient, *, movie_slug: str, title: str,
    duration: float | None, extra_slug: str | None = None, is_extra: bool = False,
    is_official_trailer: bool = False,
) -> PlaybackSelection:
    if not is_extra:
        playback = client.get_movie_playback(movie_slug)
        if not playback.has_video or not playback.video_url:
            raise MediaUnavailableError(f"The Daily Wire provides no playable video for '{title}'")
        if playback.trailer_url and playback.video_url == playback.trailer_url:
            raise MediaUnavailableError(f"The connected account does not provide access to the full movie '{title}'")
        if duration and playback.duration and playback.duration < duration * 0.5:
            raise MediaUnavailableError(f"The Daily Wire returned only a preview for '{title}', not the full movie")
        return PlaybackSelection(playback.video_url)

    if not extra_slug:
        raise MediaUnavailableError("Movie extra has no Daily Wire slug")
    metadata = None
    try:
        playback = client.get_movie_extra_playback(extra_slug)
        url = playback.video_url
        metadata = getattr(playback, "metadata", None)
    except Exception:
        # A canceled request must never trigger another network call as fallback.
        # API cancellation is an InterruptedError, independent of this package.
        import sys
        if isinstance(sys.exception(), InterruptedError) or not is_official_trailer:
            raise
        url = None
    if not url and is_official_trailer:
        page = client.get_movie_page(movie_slug)
        url = page.trailer.trailer_url if page.trailer else None
    if not url:
        raise MediaUnavailableError(f"The Daily Wire provides no playable video for '{title}'")
    return PlaybackSelection(url, metadata)
