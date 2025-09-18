from __future__ import annotations

from datetime import datetime

from backend.api.models.base import RequestBase, ResponseBase


# ---------- Strict input (create/update) ----------
class _DownloadProfileSeriesAPIBaseIn(RequestBase):
    """Fields for requests: validate here if needed."""

    media_profile_id: int
    enable_profile: bool
    include_upcoming_seasons: bool


class DownloadProfileSeriesAPICreate(_DownloadProfileSeriesAPIBaseIn):
    """Request body for creating a download profile."""

    show_id: int


class DownloadProfileSeriesAPIUpdate(_DownloadProfileSeriesAPIBaseIn):
    """Request body for updating a download profile."""
    pass


# ---------- Lenient output (read) ----------
class _DownloadProfileSeriesAPIBaseOut(ResponseBase):
    """Fields for responses: no validators, no constraints."""

    media_profile_id: int
    enable_profile: bool
    include_upcoming_seasons: bool
    id: int
    show_id: int


class DownloadProfileSeriesAPIRead(_DownloadProfileSeriesAPIBaseOut):
    """Response body for a download profile."""

    created_at: datetime
    updated_at: datetime