from __future__ import annotations

from typing import Optional, Union
from datetime import datetime

from pydantic import computed_field

from backend.api.models.base import ResponseBase, RequestBase
from backend.types.episode_types import EpisodePublishStatus

from backend.utils.helpers import generate_uuid


# ---------- Strict input (create/update) ----------
class _EpisodeAPIBaseIn(RequestBase):
    """Fields for requests: validate here if needed."""
    # Fields in the episodes' table
    publish_status: EpisodePublishStatus
    went_live_date: Optional[datetime]
    published_date: Optional[datetime]
    redownloaded_date: Optional[datetime]

    # Fields in the media_items table
    title: str
    description: str
    downloaded_date: Optional[datetime]


class EpisodeAPICreate(_EpisodeAPIBaseIn):
    """Request body for creating an episode."""

    # Fields in the episodes' table
    show_id: int
    index: int

    # Fields in the media_items table
    dw_id: Optional[str]
    slug: str

    @computed_field(return_type=str)
    @property
    def uuid(self) -> str:
        return generate_uuid()


class EpisodeAPIUpdate(_EpisodeAPIBaseIn):
    """Request body for updating an episode."""

    # Fields in the media_items table
    dw_id: Optional[str]


# ---------- Lenient output (read) ----------
class _EpisodeAPIBaseOut(ResponseBase):
    """Fields for responses: no validators, keep types for doc/serialization."""

    # Fields in the episodes' table
    id: int
    show_id: int
    index: int
    publish_status: Union[EpisodePublishStatus, str]
    went_live_date: Optional[datetime]
    published_date: Optional[datetime]
    redownloaded_date: Optional[datetime]

    # Fields in the media_items table
    title: str
    description: str
    downloaded_date: Optional[datetime]
    uuid: str
    dw_id: Optional[str]
    slug: str
    background_image_path: Optional[str]
    thumbnail_landscape_path: Optional[str]
    thumbnail_portrait_path: Optional[str]
    thumbnail_square_path: Optional[str]


class EpisodeAPIRead(_EpisodeAPIBaseOut):
    """Represents an episode summary/detail item returned by the API."""

    created_at: datetime
    updated_at: datetime