from __future__ import annotations

from datetime import date, datetime

from pydantic import Field, model_validator

from backend.api.models.download_profile import DownloadProfileAPIBaseIn, DownloadProfileAPICreate, DownloadProfileAPIUpdate, \
    DownloadProfileAPIBaseOut


# ---------- Strict input (create/update) ----------
class _PodcastDownloadProfileAPIBaseIn(DownloadProfileAPIBaseIn):
    """Fields for requests: validate here (constraints allowed)."""

    download_with_countdown: bool
    redownload_final: bool
    download_days_in_past: int = Field(ge=0)
    download_episode_count: int = Field(default=0, ge=0)
    download_starting_from: date | None = None
    delete_older_episodes: bool

    @model_validator(mode="after")
    def _validate_download_limit(self):
        if self.download_days_in_past > 0 and self.download_episode_count > 0:
            raise ValueError("Choose either a date limit or an episode-count limit, not both")
        if self.download_starting_from is not None and (
            self.download_days_in_past > 0 or self.download_episode_count > 0
        ):
            raise ValueError("Download starting from can only be used when Limit by is set to No limits")
        return self


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
    download_episode_count: int
    download_starting_from: date | None
    delete_older_episodes: bool


class PodcastDownloadProfileAPIRead(_PodcastDownloadProfileAPIBaseOut):
    """Response body for a download profile for podcasts."""

    created_at: datetime
    updated_at: datetime
