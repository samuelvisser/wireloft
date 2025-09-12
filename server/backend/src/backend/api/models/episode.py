from __future__ import annotations

from typing import Optional

from pydantic import AwareDatetime, computed_field

from backend.api.models.base import ResponseBase, RequestBase
from backend.types import EpisodePublishStatus
from backend.utils.helpers import generate_uuid


class EpisodeAPIBase:
    """Fields common to all episode models."""
    # Fields in the episodes' table
    publish_status: EpisodePublishStatus
    went_live_date: Optional[AwareDatetime]
    published_date: Optional[AwareDatetime]
    redownloaded_date: Optional[AwareDatetime]

    # Fields in the media_items table
    title: str
    description: str
    downloaded_date: Optional[AwareDatetime]


class EpisodeAPICreate(EpisodeAPIBase, RequestBase):
    """Request body for creating an episode."""
    # Fields in the episodes' table
    show_id: int
    index: int

    # Fields in the media_items table
    dw_id: str
    slug: str

    @computed_field(return_type=str)
    @property
    def uuid(self) -> str:
        return generate_uuid()


class EpisodeAPIRead(EpisodeAPIBase, ResponseBase):
    """Represents an episode summary/detail item returned by the API."""
    # Fields in the episodes' table
    id: int
    show_id: int
    index: int

    # Fields in the media_items table
    uuid: str
    dw_id: str
    slug: str
    created_at: AwareDatetime
    updated_at: AwareDatetime


class EpisodeAPIUpdate(EpisodeAPIBase, RequestBase):
    """Request body for updating an episode."""
    pass