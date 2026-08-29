from __future__ import annotations

from typing import Optional
from datetime import datetime

from pydantic import computed_field

from backend.api.models.base import ResponseBase, RequestBase
from backend.utils.helpers import generate_uuid


# ---------- Strict input (create/update) ----------
class _MovieAPIBaseIn(RequestBase):
    """Fields for requests: validate here if needed."""

    # Fields in the media_items table
    title: str
    extended_title: Optional[str] = None
    description: Optional[str]
    downloaded_date: Optional[datetime]
    duration: float = 0
    background_image_path: Optional[str] = None
    thumbnail_landscape_path: Optional[str] = None
    thumbnail_portrait_path: Optional[str] = None
    thumbnail_square_path: Optional[str] = None
    sharing_url: Optional[str] = None
    author_name: Optional[str] = None
    mature_rating: Optional[str] = None
    is_downloadable: Optional[bool] = True
    trailer_slug: Optional[str] = None
    trailer_title: Optional[str] = None
    trailer_sharing_url: Optional[str] = None
    trailer_thumbnail_path: Optional[str] = None


class MovieAPICreate(_MovieAPIBaseIn):
    """Request body for creating a movie."""

    # Fields in the media_items table
    slug: str
    dw_id: Optional[str] = None

    @computed_field(return_type=str)
    @property
    def uuid(self) -> str:
        return generate_uuid()


class MovieAPIUpdate(_MovieAPIBaseIn):
    """Request body for updating a movie."""
    pass


# ---------- Lenient output (read) ----------
class _MovieAPIBaseOut(ResponseBase):
    """Fields for responses: no validators, no constraints."""

    # Fields in the media_items table
    id: int
    uuid: str
    slug: str
    title: str
    extended_title: Optional[str]
    description: Optional[str]
    downloaded_date: Optional[datetime]
    duration: float
    background_image_path: Optional[str]
    thumbnail_landscape_path: Optional[str]
    thumbnail_portrait_path: Optional[str]
    thumbnail_square_path: Optional[str]
    dw_id: Optional[str]
    sharing_url: Optional[str]
    author_name: Optional[str]
    mature_rating: Optional[str]
    is_downloadable: Optional[bool]
    trailer_slug: Optional[str]
    trailer_title: Optional[str]
    trailer_sharing_url: Optional[str]
    trailer_thumbnail_path: Optional[str]


class MovieAPIRead(_MovieAPIBaseOut):
    """Represents a movie summary/detail item returned by the API."""

    created_at: datetime
    updated_at: datetime
