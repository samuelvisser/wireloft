from __future__ import annotations

from datetime import datetime

from backend.api.models.base import RequestBase
from backend.api.models.download_profile import DownloadProfileAPIBaseIn, DownloadProfileAPICreate, DownloadProfileAPIUpdate, \
    DownloadProfileAPIBaseOut
from backend.api.models.season import SeasonAPIRequestDetached, SeasonAPIRead


# ---------- Strict input (create/update) ----------
class _SeriesDownloadProfileAPIBaseIn(DownloadProfileAPIBaseIn):
    """Fields for requests: validate here if needed."""

    seasons: list[SeasonAPIRequestDetached]
    include_upcoming_seasons: bool


class SeriesDownloadProfileAPICreateBundle(_SeriesDownloadProfileAPIBaseIn):
    """Request body for creating a download profile for series while bundleing it with a show and media profile."""
    pass


class SeriesDownloadProfileAPICreate(_SeriesDownloadProfileAPIBaseIn, DownloadProfileAPICreate):
    """Request body for creating a download profile for series."""
    pass


class SeriesDownloadProfileAPIUpdate(_SeriesDownloadProfileAPIBaseIn, DownloadProfileAPIUpdate):
    """Request body for updating a download profile for series."""
    pass


# ---------- Lenient output (read) ----------
class _SeriesDownloadProfileAPIBaseOut(DownloadProfileAPIBaseOut):
    """Fields for responses: no validators, no constraints."""

    seasons: list[SeasonAPIRead]
    include_upcoming_seasons: bool


class SeriesDownloadProfileAPIRead(_SeriesDownloadProfileAPIBaseOut):
    """Response body for a download profile for series."""

    created_at: datetime
    updated_at: datetime