from __future__ import annotations

from datetime import datetime

from pydantic import Field

from backend.api.models.download_profile import DownloadProfileAPIBaseIn, DownloadProfileAPICreate, DownloadProfileAPIUpdate, \
    DownloadProfileAPIBaseOut


# ---------- Strict input (create/update) ----------
class _PodcastDownloadProfileAPIBaseIn(DownloadProfileAPIBaseIn):
    """Fields for requests: validate here (constraints allowed)."""

    download_with_countdown: bool
    redownload_final: bool
    download_days_in_past: int = Field(ge=0)
    delete_older_episodes: bool


class PodcastDownloadProfileAPICreateBundle(_PodcastDownloadProfileAPIBaseIn):
    """Request body for creating a download profile for podcasts while bundling it with a show and media profile."""
    pass


class PodcastDownloadProfileAPICreate(_PodcastDownloadProfileAPIBaseIn, DownloadProfileAPICreate):
    """Request body for creating a download profile for podcasts."""
    pass


class PodcastDownloadProfileAPIUpdate(_PodcastDownloadProfileAPIBaseIn, DownloadProfileAPIUpdate):
    """Request body for updating a download profile for podcasts."""
    pass


# ---------- Lenient output (read) ----------
class _PodcastDownloadProfileAPIBaseOut(DownloadProfileAPIBaseOut):
    """Fields for responses: no validators, no constraints."""

    download_with_countdown: bool
    redownload_final: bool
    download_days_in_past: int
    delete_older_episodes: bool


class PodcastDownloadProfileAPIRead(_PodcastDownloadProfileAPIBaseOut):
    """Response body for a download profile for podcasts."""

    created_at: datetime
    updated_at: datetime