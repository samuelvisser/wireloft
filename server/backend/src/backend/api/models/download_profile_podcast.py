from __future__ import annotations

from datetime import datetime

from pydantic import Field

from backend.api.models.base import RequestBase, ResponseBase


# ---------- Strict input (create/update) ----------
class _DownloadProfilePodcastAPIBaseIn(RequestBase):
    """Fields for requests: validate here (constraints allowed)."""

    media_profile_id: int
    enable_profile: bool
    download_with_countdown: bool
    redownload_final: bool
    download_days_in_past: int = Field(ge=0)
    delete_older_episodes: bool


class DownloadProfilePodcastAPICreate(_DownloadProfilePodcastAPIBaseIn):
    """Request body for creating a download profile."""
    show_id: int


class DownloadProfilePodcastAPIUpdate(_DownloadProfilePodcastAPIBaseIn):
    """Request body for updating a download profile."""
    pass


# ---------- Lenient output (read) ----------
class _DownloadProfilePodcastAPIBaseOut(ResponseBase):
    """Fields for responses: no validators, no constraints."""

    id: int
    show_id: int
    media_profile_id: int
    enable_profile: bool
    download_with_countdown: bool
    redownload_final: bool
    download_days_in_past: int
    delete_older_episodes: bool


class DownloadProfilePodcastAPIRead(_DownloadProfilePodcastAPIBaseOut):
    """Response body for a download profile."""

    created_at: datetime
    updated_at: datetime