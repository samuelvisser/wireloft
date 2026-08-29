from __future__ import annotations

from typing import Optional

from pydantic import Field

from .BaseRecord import BaseRecord


class DwCatalogShowRecord(BaseRecord):
    dw_id: str
    slug: str
    title: str
    description: Optional[str] = None
    author_name: Optional[str] = None
    author_slug: Optional[str] = None
    author_headshot_path: Optional[str] = None
    background_image_path: Optional[str] = None
    logo_image_path: Optional[str] = None
    thumbnail_landscape_path: Optional[str] = None
    thumbnail_portrait_path: Optional[str] = None
    thumbnail_square_path: Optional[str] = None


class DwTrailerRecord(BaseRecord):
    dw_id: str
    slug: str
    title: str
    sharing_url: str
    duration: float = 0
    thumbnail_landscape_path: Optional[str] = None


class DwCatalogMovieRecord(BaseRecord):
    dw_id: str
    slug: str
    title: str
    extended_title: Optional[str] = None
    description: Optional[str] = None
    author_name: Optional[str] = None
    author_slug: Optional[str] = None
    background_image_path: Optional[str] = None
    logo_image_path: Optional[str] = None
    thumbnail_landscape_path: Optional[str] = None
    thumbnail_portrait_path: Optional[str] = None
    thumbnail_square_path: Optional[str] = None


class DwMovieRecord(DwCatalogMovieRecord):
    duration: float = 0
    sharing_url: str
    mature_rating: Optional[str] = None
    is_downloadable: bool = True
    available_for: list[str] = Field(default_factory=list)
    trailer: Optional[DwTrailerRecord] = None


class DwMoviePlaybackRecord(BaseRecord):
    video_url: Optional[str] = None
    trailer_url: Optional[str] = None
    duration: float = 0
    trailer_duration: float = 0
    has_video: bool = False


class DwCatalogRecord(BaseRecord):
    shows: list[DwCatalogShowRecord] = Field(default_factory=list)
    movies: list[DwCatalogMovieRecord] = Field(default_factory=list)


class DwCatalogShowPageRecord(BaseRecord):
    items: list[DwCatalogShowRecord] = Field(default_factory=list)
    offset: int = 0
    limit: int = 0
    total: int = 0
    has_more: bool = False


class DwCatalogMoviePageRecord(BaseRecord):
    items: list[DwCatalogMovieRecord] = Field(default_factory=list)
    offset: int = 0
    limit: int = 0
    total: int = 0
    has_more: bool = False
