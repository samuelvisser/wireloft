from __future__ import annotations

from datetime import datetime

from backend.api.models.base import RequestBase, ResponseBase


class DownloadProfileSeriesAPIBase:
    """Fields common to all download profile models."""

    media_profile_id: int
    enable_profile: bool
    include_upcoming_seasons: bool


class DownloadProfileSeriesAPICreate(DownloadProfileSeriesAPIBase, RequestBase):
    """Request body for creating a download profile."""
    show_id: int


class DownloadProfileSeriesAPIRead(DownloadProfileSeriesAPIBase, ResponseBase):
    """Response body for a download profile."""

    id: int
    show_id: int
    created_at: datetime
    updated_at: datetime


class DownloadProfileSeriesAPIUpdate(DownloadProfileSeriesAPIBase, RequestBase):
    """Request body for updating a download profile."""
    pass
