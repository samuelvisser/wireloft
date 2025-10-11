from __future__ import annotations

from datetime import datetime

from backend.api.models.base import RequestBase, ResponseBase
from backend.api.models.season import SeasonAPIDetached


# ---------- Strict input (create/update) ----------
class _SeriesDownloadProfileAPIBaseIn(RequestBase):
    """Fields for requests: validate here if needed."""

    enable_profile: bool
    seasons: list[SeasonAPIDetached]
    include_upcoming_seasons: bool


class SeriesDownloadProfileAPICreateBundle(_SeriesDownloadProfileAPIBaseIn):
    """Request body for creating a download profile for series while bundleing it with a show and media profile."""
    pass


class SeriesDownloadProfileAPICreate(_SeriesDownloadProfileAPIBaseIn):
    """Request body for creating a download profile for series."""

    show_id: int
    local_media_profile_id: int


class SeriesDownloadProfileAPIUpdate(_SeriesDownloadProfileAPIBaseIn):
    """Request body for updating a download profile for series."""

    local_media_profile_id: int


# ---------- Lenient output (read) ----------
class _SeriesDownloadProfileAPIBaseOut(ResponseBase):
    """Fields for responses: no validators, no constraints."""

    local_media_profile_id: int
    enable_profile: bool
    seasons: list[SeasonAPIDetached]
    include_upcoming_seasons: bool
    id: int
    show_id: int

class SeriesDownloadProfileAPIRead(_SeriesDownloadProfileAPIBaseOut):
    """Response body for a download profile for series."""

    created_at: datetime
    updated_at: datetime