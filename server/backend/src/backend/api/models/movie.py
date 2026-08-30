from __future__ import annotations

from typing import Optional
from datetime import date, datetime

from pydantic import Field, computed_field

from backend.api.models.base import ResponseBase, RequestBase
from backend.api.models.movie_extra import MovieExtraAPICreate, MovieExtraAPIRead
from backend.utils.helpers import generate_uuid


# ---------- Strict input (create/update) ----------
class _MovieAPIBaseIn(RequestBase):
    """Fields for requests: validate here if needed."""

    # Fields in the media_items table
    title: str
    extended_title: Optional[str] = None
    description: Optional[str] = None
    downloaded_date: Optional[datetime] = None
    duration: float = 0
    background_image_path: Optional[str] = None
    thumbnail_landscape_path: Optional[str] = None
    thumbnail_portrait_path: Optional[str] = None
    thumbnail_square_path: Optional[str] = None
    sharing_url: Optional[str] = None
    author_name: Optional[str] = None
    author_slug: Optional[str] = None
    logo_image_path: Optional[str] = None
    mature_rating: Optional[str] = None
    is_downloadable: Optional[bool] = True
    available_for: list[str] = Field(default_factory=list)


class MovieAPICreate(_MovieAPIBaseIn):
    """Request body for creating a movie."""

    # Fields in the media_items table
    slug: str
    dw_id: Optional[str] = None
    movie_extras: list[MovieExtraAPICreate] = Field(default_factory=list)
    # The extra rows do not have database IDs until this request is persisted,
    # so create requests identify the official trailer by its stable DW slug.
    official_trailer_slug: Optional[str] = None

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
    author_slug: Optional[str]
    logo_image_path: Optional[str]
    mature_rating: Optional[str]
    is_downloadable: Optional[bool]
    available_for: list[str]
    release_date: Optional[date]
    release_date_source: Optional[str]
    release_date_source_id: Optional[str]
    release_date_lookup_status: str
    release_date_lookup_attempted_at: Optional[datetime]
    release_date_lookup_error: Optional[str]
    official_trailer_id: Optional[int]
    official_trailer: Optional[MovieExtraAPIRead]
    movie_extras: list[MovieExtraAPIRead]


class MovieAPIRead(_MovieAPIBaseOut):
    """Represents a movie summary/detail item returned by the API."""

    created_at: datetime
    updated_at: datetime
