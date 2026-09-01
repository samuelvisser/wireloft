from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import computed_field

from backend.api.models.base import RequestBase, ResponseBase
from backend.types.media_types import MovieExtraType
from backend.utils.helpers import generate_uuid


class _MovieExtraAPIBaseIn(RequestBase):
    title: str
    movie_extra_type: MovieExtraType
    description: Optional[str] = None
    downloaded_date: Optional[datetime] = None
    duration: float = 0
    background_image_path: Optional[str] = None
    thumbnail_landscape_path: Optional[str] = None
    thumbnail_portrait_path: Optional[str] = None
    thumbnail_square_path: Optional[str] = None
    dw_id: Optional[str] = None
    slug: str
    sharing_url: Optional[str] = None
    published_date: Optional[datetime] = None


class MovieExtraAPICreate(_MovieExtraAPIBaseIn):
    """Movie-extra metadata; the owning movie is supplied by the service."""

    @computed_field(return_type=str)
    @property
    def uuid(self) -> str:
        return generate_uuid()


class MovieExtraAPIUpdate(_MovieExtraAPIBaseIn):
    pass


class MovieExtraAPIRead(ResponseBase):
    id: int
    movie_id: int
    uuid: str
    movie_extra_type: MovieExtraType
    title: str
    description: Optional[str]
    downloaded_date: Optional[datetime]
    duration: float
    background_image_path: Optional[str]
    thumbnail_landscape_path: Optional[str]
    thumbnail_portrait_path: Optional[str]
    thumbnail_square_path: Optional[str]
    dw_id: Optional[str]
    slug: str
    sharing_url: Optional[str]
    published_date: Optional[datetime]
    created_at: datetime
    updated_at: datetime
