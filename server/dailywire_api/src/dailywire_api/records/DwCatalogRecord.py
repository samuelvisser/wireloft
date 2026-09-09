from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal, Optional

from pydantic import (
    AliasChoices,
    AliasPath,
    AwareDatetime,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

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

        original_title = str(data.get("title") or "").strip()
        normalized_title = _normalize_catalog_title(
            original_title,
            data.get("description"),
        )
        updates: dict[str, Any] = {}

        if normalized_title != data.get("title"):
            updates["title"] = normalized_title

        if (
            "extended_title" in cls.model_fields
            and "extended_title" not in data
            and "extendedTitle" not in data
        ):
            updates["extended_title"] = original_title or normalized_title

        return {**data, **updates} if updates else data


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


class DwMovieImagesRecord(BaseRecord):
    movie_app_background_image: Optional[str] = None
    movie_logo_image: Optional[str] = None
    movie_ott_background_image: Optional[str] = None
    movie_poster_image: Optional[str] = None
    movie_thumbnail_image: Optional[str] = None
    movie_web_background_image: Optional[str] = None


class DwMovieExtraImagesRecord(BaseRecord):
    extra_thumbnail_image: Optional[str] = None


class DwMovieCastAndCrewRecord(BaseRecord):
    name: str
    image_size: Optional[str] = None
    image_url: Optional[str] = None
    info: Optional[str] = None
    role_text: Optional[str] = None


class DwMovieHostImagesRecord(BaseRecord):
    host_app_background_image: Optional[str] = None
    host_image_1x1: Optional[str] = None
    host_logo_image: Optional[str] = None
    host_ott_background_image: Optional[str] = None
    host_web_background_image: Optional[str] = None


class DwMovieHostRecord(BaseRecord):
    images: DwMovieHostImagesRecord = Field(default_factory=DwMovieHostImagesRecord)
    dw_id: Optional[str] = Field(
        validation_alias=AliasChoices("pid", "id", "dwID", "dwId"),
        default=None,
    )
    name: str
    slug: str


class DwRelatedContentImagesRecord(BaseRecord):
    movie_app_background_image: Optional[str] = None
    movie_logo_image: Optional[str] = None
    movie_ott_background_image: Optional[str] = None
    movie_poster_image: Optional[str] = None
    movie_thumbnail_image: Optional[str] = None
    movie_web_background_image: Optional[str] = None
    show_logo_image: Optional[str] = None
    show_ott_background_image: Optional[str] = None
    show_ott_episode_background_image: Optional[str] = None
    show_poster_image: Optional[str] = None
    show_thumbnail_image: Optional[str] = None
    show_web_background_image: Optional[str] = None


class DwRelatedContentRecord(BaseRecord):
    images: DwRelatedContentImagesRecord = Field(default_factory=DwRelatedContentImagesRecord)
    content_type: str
    published_at: Optional[AwareDatetime] = None
    slug: str
    title: str


class DwMovieExtraRecord(BaseRecord):
    dw_id: Optional[str] = Field(
        validation_alias=AliasChoices("pid", "id", "dwID", "dwId"),
        default=None,
    )
    slug: str
    title: str
    movie_extra_type: MovieExtraTypeValue = "other"
    description: Optional[str] = None
    sharing_url: Optional[str] = None
    published_date: Optional[AwareDatetime] = Field(
        validation_alias=AliasChoices("publishedAt", "publishedDate", "published_date"),
        default=None,
    )
    duration: float = 0
    available_for: list[str] = Field(default_factory=list)
    images: DwMovieExtraImagesRecord = Field(default_factory=DwMovieExtraImagesRecord)
    background_image_path: Optional[str] = None
    thumbnail_landscape_path: Optional[str] = Field(
        validation_alias=AliasChoices(
            "thumbnailLandscapePath",
            AliasPath("images", "extra_thumbnail_image"),
        ),
        default=None,
    )
    thumbnail_portrait_path: Optional[str] = None
    thumbnail_square_path: Optional[str] = None

    # The dedicated trailer object enriches the matching extra with fresh
    # playback data. Retain it in the API record, but never persist signed tokens.
    continue_watching_entity_id: Optional[str] = None
    continue_watching_entity_type: Optional[str] = None
    mux_drm_token: Optional[str] = None
    mux_playback_id: Optional[str] = None
    mux_playback_token: Optional[str] = None
    playback_policy: Optional[str] = None
    trailer_url: Optional[str] = None

    @field_validator("published_date", mode="before")
    @classmethod
    def assume_utc_for_naive_dailywire_timestamp(cls, value: Any) -> Any:
        """Daily Wire has historically omitted UTC suffixes on some extra dates."""
        if isinstance(value, datetime):
            return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        if not isinstance(value, str) or not value.strip():
            return value

        normalized = value.strip()
        if normalized.endswith(("Z", "z")):
            normalized = normalized[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return value
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


class DwCatalogMovieRecord(_CatalogTitleRecord):
    dw_id: str = Field(validation_alias=AliasChoices("id", "dwID", "dwId"))
    slug: str
    extended_title: Optional[str] = None
    author_name: Optional[str] = Field(
        validation_alias=AliasChoices(
            "authorName",
            AliasPath("host", "name"),
            AliasPath("author", "name"),
        ),
        default=None,
    )
    author_slug: Optional[str] = Field(
        validation_alias=AliasChoices(
            "authorSlug",
            AliasPath("host", "slug"),
            AliasPath("author", "slug"),
        ),
        default=None,
    )
    background_image_path: Optional[str] = Field(
        validation_alias=AliasChoices("backgroundImage", "backgroundImagePath"),
        default=None,
    )
    logo_image_path: Optional[str] = Field(
        validation_alias=AliasChoices("logoImage", "logoImagePath"),
        default=None,
    )
    thumbnail_landscape_path: Optional[str] = Field(
        validation_alias=AliasChoices(
            "thumbnailLandscapePath",
            AliasPath("images", "thumbnail", "land"),
        ),
        default=None,
    )
    thumbnail_portrait_path: Optional[str] = Field(
        validation_alias=AliasChoices(
            "thumbnailPortraitPath",
            AliasPath("images", "thumbnail", "port"),
        ),
        default=None,
    )
    thumbnail_square_path: Optional[str] = Field(
        validation_alias=AliasChoices(
            "thumbnailSquarePath",
            AliasPath("images", "thumbnail", "square"),
        ),
        default=None,
    )


class DwMovieRecord(DwCatalogMovieRecord):
    dw_id: str = Field(validation_alias=AliasChoices("pid", "id", "dwID", "dwId"))
    duration: float = Field(validation_alias=AliasChoices("runtime", "duration"), default=0)
    sharing_url: str
    mature_rating: Optional[str] = Field(
        validation_alias=AliasChoices("rating", "matureRating"),
        default=None,
    )
    author_name: Optional[str] = Field(
        validation_alias=AliasChoices(
            "authorName",
            AliasPath("hosts", 0, "name"),
            AliasPath("host", "name"),
            AliasPath("author", "name"),
        ),
        default=None,
    )
    author_slug: Optional[str] = Field(
        validation_alias=AliasChoices(
            "authorSlug",
            AliasPath("hosts", 0, "slug"),
            AliasPath("host", "slug"),
            AliasPath("author", "slug"),
        ),
        default=None,
    )
    background_image_path: Optional[str] = Field(
        validation_alias=AliasChoices(
            "backgroundImage",
            "backgroundImagePath",
            AliasPath("images", "movie_web_background_image"),
            AliasPath("images", "movie_app_background_image"),
        ),
        default=None,
    )
    logo_image_path: Optional[str] = Field(
        validation_alias=AliasChoices(
            "logoImage",
            "logoImagePath",
            AliasPath("images", "movie_logo_image"),
        ),
        default=None,
    )
    thumbnail_landscape_path: Optional[str] = Field(
        validation_alias=AliasChoices(
            "thumbnailLandscapePath",
            AliasPath("images", "movie_thumbnail_image"),
        ),
        default=None,
    )
    thumbnail_portrait_path: Optional[str] = Field(
        validation_alias=AliasChoices(
            "thumbnailPortraitPath",
            AliasPath("images", "movie_poster_image"),
        ),
        default=None,
    )
    thumbnail_square_path: Optional[str] = None

    has_video: bool = False
    is_downloadable: bool = False
    images: DwMovieImagesRecord = Field(default_factory=DwMovieImagesRecord)
    background: Optional[str] = None
    byline: Optional[str] = None
    language: Optional[str] = None
    origin_country: Optional[str] = None
    published_at: Optional[AwareDatetime] = None
    status: str = "unknown"
    available_for: list[str] = Field(default_factory=list)
    cast_and_crew: list[DwMovieCastAndCrewRecord] = Field(default_factory=list)
    directed_by: list[str] = Field(default_factory=list)
    movie_extras: list[DwMovieExtraRecord] = Field(
        validation_alias=AliasChoices("extras", "movieExtras", "movie_extras"),
        default_factory=list,
    )
    # The supplied samples do not reveal the element schema for these currently
    # empty collections. Retain their JSON losslessly until Daily Wire exposes an
    # example that can be modeled more narrowly.
    genres: list[Any] = Field(default_factory=list)
    hosts: list[DwMovieHostRecord] = Field(default_factory=list)
    more_like_this: list[DwRelatedContentRecord] = Field(default_factory=list)
    production_companies: list[Any] = Field(default_factory=list)
    shop_items: list[Any] = Field(default_factory=list)
    starring: list[str] = Field(default_factory=list)
    written_by: list[str] = Field(default_factory=list)
    trailer: Optional[DwMovieExtraRecord] = None

    @field_validator("duration", mode="before")
    @classmethod
    def normalize_runtime(cls, value: Any) -> float:
        return 0 if value is None else value

    @computed_field(return_type=bool)
    @property
    def is_upcoming(self) -> bool:
        return self.status.casefold() == "scheduled"

    @computed_field(return_type=Optional[date])
    @property
    def expected_release_date(self) -> Optional[date]:
        if not self.is_upcoming or self.published_at is None:
            return None
        return self.published_at.date()


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
