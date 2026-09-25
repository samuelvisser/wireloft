from __future__ import annotations

from datetime import datetime
from typing import Union

from pydantic import AliasPath, Field

from backend.api.models.base import ResponseBase, response_model_config
from backend.api.models.rss_stream_profile import RssStreamProfileAPIRead
from backend.types.stream_profile_types import StreamProfileType


class StreamProfileAPIRead(ResponseBase):
    """Unified response body for a stream profile (any type).

    Represents the base stream profile record with its discriminator `type`.
    Create/Update/Delete of concrete profiles should be done via the
    type-specific endpoints (e.g., RSS).
    """

    model_config = response_model_config(nested_source="profile")

    id: int
    show_id: int
    enable_profile: bool
    use_downloads: bool
    use_dw_stream: bool
    preferred_format: str
    prefer_exact_match: bool
    ep_id_type_list: list[str]
    type: StreamProfileType

    created_at: datetime
    updated_at: datetime


class StreamProfileAPIReadView(StreamProfileAPIRead):
    """Denormalized stream-profile view sourced from ORM relationships."""

    show_title: str = Field(validation_alias=AliasPath("profile", "show", "title"))
    show_slug: str = Field(validation_alias=AliasPath("profile", "show", "slug"))
    stream_profile_impl: RssStreamProfileAPIRead = Field(
        validation_alias="profile"
    )
