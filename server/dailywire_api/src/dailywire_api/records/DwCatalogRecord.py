from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import AwareDatetime, Field, model_validator

from .BaseRecord import BaseRecord


def _normalize_catalog_title(title: object, description: object) -> str:
    """Remove browse-page marketing copy from a Daily Wire catalog title."""
    original = str(title or "").strip()
    normalized = original
    description_text = str(description or "").strip()

    if description_text and normalized.casefold().endswith(description_text.casefold()):
        normalized = normalized[:len(normalized) - len(description_text)].rstrip()
        normalized = normalized.rstrip("|").rstrip()

    if " | " in normalized:
        normalized = normalized.split(" | ", 1)[0].strip()

    return normalized or original


class _CatalogTitleRecord(BaseRecord):
    title: str
    description: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_catalog_title(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        normalized_title = _normalize_catalog_title(
            data.get("title"),
            data.get("description"),
        )
        if normalized_title == data.get("title"):
            return data

        return {**data, "title": normalized_title}


class DwCatalogShowRecord(_CatalogTitleRecord):
    dw_id: str
    slug: str
    author_name: Optional[str] = None
    author_slug: Optional[str] = None
    author_headshot_path: Optional[str] = None
    background_image_path: Optional[str] = None
    logo_image_path: Optional[str] = None
    thumbnail_landscape_path: Optional[str] = None
    thumbnail_portrait_path: Optional[str] = None
    thumbnail_square_path: Optional[str] = None


MovieExtraTypeValue = Literal[
    "behindthescenes",
    "deleted",
    "featurette",
    "interview",
    "scene",
    "short",
    "trailer",
    "other",
]


class DwMovieExtraRecord(BaseRecord):
    dw_id: Optional[str] = None
    slug: str
    title: str
    movie_extra_type: MovieExtraTypeValue
    description: Optional[str] = None
    sharing_url: Optional[str] = None
    published_date: Optional[AwareDatetime] = Field(validation_alias="publishedAt", default=None)
    duration: float = 0
    background_image_path: Optional[str] = None
    thumbnail_landscape_path: Optional[str] = None
    thumbnail_portrait_path: Optional[str] = None
    thumbnail_square_path: Optional[str] = None


class DwCatalogMovieRecord(_CatalogTitleRecord):
    dw_id: str
    slug: str
    extended_title: Optional[str] = None
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
    movie_extras: list[DwMovieExtraRecord] = Field(default_factory=list)
    # Kept as the dedicated official-trailer field consumed by the prominent
    # movie-page actions. It points to the matching item in movie_extras.
    trailer: Optional[DwMovieExtraRecord] = None


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
