from __future__ import annotations

from typing import Optional, Union
from datetime import datetime

from pydantic import AwareDatetime, computed_field

from backend.api.models.base import ResponseBase, RequestBase
from backend.types.episode_types import EpisodePublishStatus

from backend.utils.helpers import generate_uuid


# ---------- Strict input (create/update) ----------
class _EpisodeAPIBaseIn(RequestBase):
    """Fields for requests: validate here if needed."""
    # Episode lifecycle/context fields
    publish_status: EpisodePublishStatus
    went_live_date: Optional[AwareDatetime]
    published_date: Optional[AwareDatetime]
    redownloaded_date: Optional[AwareDatetime]

    # Reusable content metadata plus MediaItem placement state
    title: str
    description: str
    downloaded_date: Optional[AwareDatetime]


class EpisodeAPICreate(_EpisodeAPIBaseIn):
    """Request body for creating an episode."""

    show_id: int
    index: int
    slug: str

    @computed_field(return_type=str)
    @property
    def uuid(self) -> str:
        return generate_uuid()


class EpisodeAPIUpdate(_EpisodeAPIBaseIn):
    """Request body for updating an episode."""
    pass

# ---------- Lenient output (read) ----------
class _EpisodeAPIBaseOut(ResponseBase):
    """Fields for responses: no validators, keep types for doc/serialization."""

    id: int
    show_id: int
    season_id: int
    index: int
    episode_identifier: str
    publish_status: Union[EpisodePublishStatus, str]
    went_live_date: Optional[datetime]
    published_date: Optional[datetime]
    scheduled_date: Optional[datetime]
    redownloaded_date: Optional[datetime]
    sharing_url: str
    early_delete_available: bool = False

    title: str
    description: str
    duration: float
    downloaded_date: Optional[datetime]
    uuid: str
    slug: str
    background_image_path: Optional[str]
    thumbnail_landscape_path: Optional[str]
    thumbnail_portrait_path: Optional[str]
    thumbnail_square_path: Optional[str]


class EpisodeAPIRead(_EpisodeAPIBaseOut):
    """Represents an episode summary/detail item returned by the API."""

    created_at: datetime
    updated_at: datetime
