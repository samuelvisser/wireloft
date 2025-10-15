from __future__ import annotations

from datetime import datetime
from typing import Union

from backend.api.models.base import ResponseBase
from backend.api.models.rss_stream_profile import RssStreamProfileAPIRead
from backend.types.stream_profile_types import StreamProfileType


class StreamProfileAPIRead(ResponseBase):
    """Unified response body for a stream profile (any type).

    Represents the base stream profile record with its discriminator `type`.
    Create/Update/Delete of concrete profiles should be done via the
    type-specific endpoints (e.g., RSS).
    """

    id: int
    show_id: int
    enable_profile: bool
    use_downloads: bool
    use_dw_stream: bool
    preferred_format: str
    require_exact_match: bool
    type: StreamProfileType

    created_at: datetime
    updated_at: datetime


class StreamProfileAPIReadView(StreamProfileAPIRead):
    """Denormalized view for a stream profile adding related display fields.

    Extends StreamProfileAPIRead with:
    - show_title: the title of the related show
    - stream_profile_impl: the concrete profile payload (e.g., RSS)
    """

    show_title: str
    show_slug: str
    stream_profile_impl: Union[RssStreamProfileAPIRead]
