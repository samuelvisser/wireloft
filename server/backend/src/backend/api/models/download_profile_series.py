from __future__ import annotations

from datetime import datetime

from backend.api.models.base import RequestBase, ResponseBase
from backend.api.models.season import SeasonAPIDetached


# ---------- Strict input (create/update) ----------
class _DownloadProfileSeriesAPIBaseIn(RequestBase):
    """Fields for requests: validate here if needed."""

    enable_profile: bool
    seasons: list[SeasonAPIDetached]
    include_upcoming_seasons: bool


class DownloadProfileSeriesAPICreateBundle(_DownloadProfileSeriesAPIBaseIn):
    """Request body for creating a download profile for series while bundleing it with a show and media profile."""
    pass


class DownloadProfileSeriesAPICreate(_DownloadProfileSeriesAPIBaseIn):
    """Request body for creating a download profile for series."""

    show_id: int
    media_profile_id: int


class DownloadProfileSeriesAPIUpdate(_DownloadProfileSeriesAPIBaseIn):
    """Request body for updating a download profile for series."""

    media_profile_id: int


# ---------- Lenient output (read) ----------
class _DownloadProfileSeriesAPIBaseOut(ResponseBase):
    """Fields for responses: no validators, no constraints."""

    media_profile_id: int
    enable_profile: bool
    seasons: list[SeasonAPIDetached]
    include_upcoming_seasons: bool
    id: int
    show_id: int

class DownloadProfileSeriesAPIRead(_DownloadProfileSeriesAPIBaseOut):
    """Response body for a download profile for series."""

    created_at: datetime
    updated_at: datetime