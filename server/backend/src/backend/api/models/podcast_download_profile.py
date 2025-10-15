from __future__ import annotations

from datetime import datetime

from pydantic import Field

from backend.api.models.base import RequestBase, ResponseBase


# ---------- Strict input (create/update) ----------
class _PodcastDownloadProfileAPIBaseIn(RequestBase):
    """Fields for requests: validate here (constraints allowed)."""

    enable_profile: bool
    download_with_countdown: bool
    redownload_final: bool
    download_days_in_past: int = Field(ge=0)
    delete_older_episodes: bool


class PodcastDownloadProfileAPICreateBundle(_PodcastDownloadProfileAPIBaseIn):
    """Request body for creating a download profile for podcasts while bundleing it with a show and media profile."""
    pass


class PodcastDownloadProfileAPICreate(_PodcastDownloadProfileAPIBaseIn):
    """Request body for creating a download profile for podcasts."""

    show_id: int
    local_media_profile_id: int


class PodcastDownloadProfileAPIUpdate(_PodcastDownloadProfileAPIBaseIn):
    """Request body for updating a download profile for podcasts."""

    local_media_profile_id: int


# ---------- Lenient output (read) ----------
class _PodcastDownloadProfileAPIBaseOut(ResponseBase):
    """Fields for responses: no validators, no constraints."""

    id: int
    show_id: int
    local_media_profile_id: int
    type: str
    enable_profile: bool
    download_with_countdown: bool
    redownload_final: bool
    download_days_in_past: int
    delete_older_episodes: bool


class PodcastDownloadProfileAPIRead(_PodcastDownloadProfileAPIBaseOut):
    """Response body for a download profile for podcasts."""

    created_at: datetime
    updated_at: datetime