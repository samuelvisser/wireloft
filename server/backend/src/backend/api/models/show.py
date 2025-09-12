from typing import Optional

from pydantic import AwareDatetime, computed_field

from backend.api.models.base import RequestBase, ResponseBase
from backend.types.show_types import ShowType, EpisodeIdentifier
from backend.utils.helpers import generate_uuid


class ShowAPIBase:
    """Fields common to all show models."""
    title: str
    description: str
    url: str
    author_name: str
    author_headshot_path: Optional[str] = None
    background_image_path: Optional[str] = None
    logo_image_path: Optional[str] = None
    thumbnail_landscape_path: Optional[str] = None
    thumbnail_portrait_path: Optional[str] = None
    thumbnail_square_path: Optional[str] = None


class ShowAPICreate(ShowAPIBase, RequestBase):
    """Request body for creating a show."""
    dw_id: str
    slug: str
    type: ShowType
    episode_identifier: EpisodeIdentifier
    author_slug: str

    @computed_field(return_type=str)
    @property
    def uuid(self) -> str:
        return generate_uuid()


class ShowAPIRead(ShowAPIBase, ResponseBase):
    """Response body for a show."""

    id: int
    uuid: str
    dw_id: str
    slug: str
    type: ShowType
    episode_identifier: EpisodeIdentifier
    author_slug: str
    years: Optional[str] = None
    created_at: AwareDatetime
    updated_at: AwareDatetime


class ShowAPIUpdate(ShowAPIBase, RequestBase):
    """Request body for updating a show."""
    pass