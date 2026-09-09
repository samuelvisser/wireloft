from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from pydantic import AwareDatetime, Field, computed_field

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
    downloaded_date: Optional[AwareDatetime] = None
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
    has_video: bool = False
    is_downloadable: Optional[bool] = True
    status: Optional[str] = None
    published_at: Optional[AwareDatetime] = None
    background: Optional[str] = None
    byline: Optional[str] = None
    language: Optional[str] = None
    origin_country: Optional[str] = None
    images: dict[str, Any] = Field(default_factory=dict)
    available_for: list[str] = Field(default_factory=list)
    cast_and_crew: list[dict[str, Any]] = Field(default_factory=list)
    directed_by: list[str] = Field(default_factory=list)
    genres: list[Any] = Field(default_factory=list)
    hosts: list[dict[str, Any]] = Field(default_factory=list)
    more_like_this: list[dict[str, Any]] = Field(default_factory=list)
    production_companies: list[Any] = Field(default_factory=list)
    shop_items: list[Any] = Field(default_factory=list)
    starring: list[str] = Field(default_factory=list)
    written_by: list[str] = Field(default_factory=list)


class MovieAPICreate(_MovieAPIBaseIn):
    """Request body for creating a movie."""

    slug: str
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
    sharing_url: Optional[str]
    author_name: Optional[str]
    author_slug: Optional[str]
    logo_image_path: Optional[str]
    mature_rating: Optional[str]
    has_video: bool
    is_downloadable: Optional[bool]
    status: Optional[str]
    published_at: Optional[datetime]
    background: Optional[str]
    byline: Optional[str]
    language: Optional[str]
    origin_country: Optional[str]
    images: dict[str, Any]
    available_for: list[str]
    cast_and_crew: list[dict[str, Any]]
    directed_by: list[str]
    genres: list[Any]
    hosts: list[dict[str, Any]]
    more_like_this: list[dict[str, Any]]
    production_companies: list[Any]
    shop_items: list[Any]
    starring: list[str]
    written_by: list[str]
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
