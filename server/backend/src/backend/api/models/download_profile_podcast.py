from __future__ import annotations

from datetime import datetime

from backend.api.models.base import RequestBase, ResponseBase


class DownloadProfilePodcastAPIBase:
    """Fields common to all download profile models."""

    media_profile_id: int
    enable_profile: bool
    download_with_countdown: bool
    redownload_final: bool
    download_days_in_past: int
    delete_older_episodes: bool


class DownloadProfilePodcastAPICreate(DownloadProfilePodcastAPIBase, RequestBase):
    """Request body for creating a download profile."""
    show_id: int


class DownloadProfilePodcastAPIRead(DownloadProfilePodcastAPIBase, ResponseBase):
    """Response body for a download profile."""

    id: int
    show_id: int
    created_at: datetime
    updated_at: datetime


class DownloadProfilePodcastAPIUpdate(DownloadProfilePodcastAPIBase, RequestBase):
    """Request body for updating a download profile."""
    pass
