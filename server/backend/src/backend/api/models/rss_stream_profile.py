from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import Field

from backend.api.models.base import RequestBase, ResponseBase
from backend.types.stream_profile_types import RssDwVideoMethod


# ---------- Strict input (create/update) ----------
class _RssStreamProfileAPIBaseIn(RequestBase):
    """Fields for requests: validate here (constraints allowed)."""

    enable_profile: bool
    use_downloads: bool
    use_dw_stream: bool
    preferred_format: str = Field(min_length=1)
    require_exact_match: bool
    dw_video_method: RssDwVideoMethod = RssDwVideoMethod.PODCASTING_2_0.value


class RssStreamProfileAPICreate(_RssStreamProfileAPIBaseIn):
    """Request body for creating an RSS stream profile.

    ``feed_url`` is optional: leave it unset (or blank) to have WireLoft
    generate one automatically from the request host and the profile's
    secret token. It can always be edited afterwards.
    """

    show_id: int
    feed_url: Optional[str] = None


class RssStreamProfileAPIUpdate(_RssStreamProfileAPIBaseIn):
    """Request body for updating an RSS stream profile."""

    feed_url: str = Field(min_length=1)


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
    dw_video_method: str
    feed_url: str


class RssStreamProfileAPIRead(_RssStreamProfileAPIBaseOut):
    """Response body for an RSS stream profile."""

    created_at: datetime
    updated_at: datetime
