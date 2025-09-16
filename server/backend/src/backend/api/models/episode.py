from __future__ import annotations

from typing import Optional
from datetime import datetime

from pydantic import computed_field

from backend.api.models.base import ResponseBase, RequestBase
from backend.types.episode_types import EpisodePublishStatus

from backend.utils.helpers import generate_uuid


class _EpisodeAPIBase:
    """Fields common to all episode models."""
    # Fields in the episodes' table
    publish_status: EpisodePublishStatus
    went_live_date: Optional[datetime]
    published_date: Optional[datetime]
    redownloaded_date: Optional[datetime]

    # Fields in the media_items table
    title: str
    description: str
    downloaded_date: Optional[datetime]


class EpisodeAPICreate(_EpisodeAPIBase, RequestBase):
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


class EpisodeAPIRead(_EpisodeAPIBase, ResponseBase):
    """Represents an episode summary/detail item returned by the API."""
    # Fields in the episodes' table
    id: int
    show_id: int
    index: int

    # Fields in the media_items table
    uuid: str
    dw_id: Optional[str]
    slug: str
    created_at: datetime
    updated_at: datetime


class EpisodeAPIUpdate(_EpisodeAPIBase, RequestBase):
    """Request body for updating an episode."""
    # Fields in the media_items table
    dw_id: Optional[str]