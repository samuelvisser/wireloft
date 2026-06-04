from __future__ import annotations

from typing import Optional, Union
from datetime import datetime

from pydantic import computed_field, Field

from backend.api.models.base import RequestBase, ResponseBase
from backend.types.dailywire_user_info import WlDwMembershipLevel
from backend.types.show_types import ShowType, EpisodeIdentifier
from backend.utils.helpers import generate_uuid


# ---------- Strict input (create/update) ----------
class _ShowAPIBaseIn(RequestBase):
    """Fields for requests: validate here if needed."""

    title: str
    description: str
    sharing_url: str
    membership_level: str
    author_name: str
    author_headshot_path: Optional[str] = None
    background_image_path: Optional[str] = None
    logo_image_path: Optional[str] = None
    thumbnail_landscape_path: Optional[str] = None
    thumbnail_portrait_path: Optional[str] = None
    thumbnail_square_path: Optional[str] = None


class ShowAPICreate(_ShowAPIBaseIn):
    """Request body for creating a show."""

    slug: str
    membership_level: WlDwMembershipLevel
    type: ShowType
    episode_identifier: EpisodeIdentifier
    author_slug: str

    @computed_field(return_type=str)
    @property
    def uuid(self) -> str:
        return generate_uuid()


class ShowAPIUpdate(_ShowAPIBaseIn):
    """Request body for updating a show."""
    pass


# ---------- Lenient output (read) ----------
class _ShowAPIBaseOut(ResponseBase):
    """Fields for responses: no validators, no constraints."""

    id: int
    uuid: str
    slug: str
    membership_level: Union[WlDwMembershipLevel, str]
    type: Union[ShowType, str]
    episode_identifier: Union[EpisodeIdentifier, str]
    author_slug: str
    title: str
    description: str
    sharing_url: str
    author_name: str
    author_headshot_path: Optional[str] = None
    background_image_path: Optional[str] = None
    logo_image_path: Optional[str] = None
    thumbnail_landscape_path: Optional[str] = None
    thumbnail_portrait_path: Optional[str] = None
    thumbnail_square_path: Optional[str] = None


class ShowAPIRead(_ShowAPIBaseOut):
    """Response body for a show."""
    created_at: datetime
    updated_at: datetime


class ShowAPIReadView(ShowAPIRead):
    """Response body for a show view."""

    episode_count: int = Field(default=0)
    years: str = Field(default="")