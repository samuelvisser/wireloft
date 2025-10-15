from __future__ import annotations

from datetime import datetime

from pydantic import Field

from backend.api.models.base import RequestBase, ResponseBase


# ---------- Strict input (create/update) ----------
class _RssStreamProfileAPIBaseIn(RequestBase):
    """Fields for requests: validate here (constraints allowed)."""

    enable_profile: bool
    use_downloads: bool
    use_dw_stream: bool
    preferred_format: str = Field(min_length=1)
    require_exact_match: bool
    feed_url: str = Field(min_length=1)


class RssStreamProfileAPICreate(_RssStreamProfileAPIBaseIn):
    """Request body for creating an RSS stream profile."""

    show_id: int


class RssStreamProfileAPIUpdate(_RssStreamProfileAPIBaseIn):
    """Request body for updating an RSS stream profile."""
    pass


# ---------- Lenient output (read) ----------
class _RssStreamProfileAPIBaseOut(ResponseBase):
    """Fields for responses: no validators, no constraints."""

    id: int
    show_id: int
    enable_profile: bool
    use_downloads: bool
    use_dw_stream: bool
    preferred_format: str
    require_exact_match: bool
    feed_url: str


class RssStreamProfileAPIRead(_RssStreamProfileAPIBaseOut):
    """Response body for an RSS stream profile."""

    created_at: datetime
    updated_at: datetime
