from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal, Optional

from pydantic import AliasChoices, AliasPath, AwareDatetime, Field, field_validator, model_validator

from .BaseRecord import BaseRecord


_UPCOMING_MARKER_RE = re.compile(
    r"\b(?:coming|premieres?|premiering)\b|\bwatch\s+exclusively\b",
    re.IGNORECASE,
)
_UPCOMING_DATE_RE = re.compile(
    r"\b(?:coming|premieres?|premiering|available|watch(?:\s+exclusively)?)\b"
    r"[^.!?\n]{0,160}?"
    r"\b(?P<month>january|february|march|april|may|june|july|august|september|october|november|december)"
    r"\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?(?:,\s*(?P<year>\d{4}))?\b",
    re.IGNORECASE,
)
_MONTH_NUMBERS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


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


def _expected_release_date(description: object, *, today: Optional[date] = None) -> Optional[date]:
    """Extract a conservative Daily Wire availability date from upcoming copy.

    The movie-detail API does not currently expose a structured release date for
    upcoming movies. It does, however, put dates such as ``September 16`` in text
    like ``Coming exclusively to The Daily Wire, September 16``. Only dates that
    occur in explicit upcoming/availability wording are considered so unrelated
    dates in a synopsis are not mistaken for a release date.
    """
    text = str(description or "").strip()
    match = _UPCOMING_DATE_RE.search(text)
    if match is None:
        return None

    month = _MONTH_NUMBERS[match.group("month").casefold()]
    day = int(match.group("day"))
    year_text = match.group("year")
    reference = today or date.today()

    try:
        if year_text:
            return date(int(year_text), month, day)

        candidate = date(reference.year, month, day)
        # A recently passed advertised date can simply mean Daily Wire has not
        # flipped the movie live yet. Only roll to the next year when the date is
        # clearly from the previous season.
        if candidate < reference - timedelta(days=120):
            candidate = date(reference.year + 1, month, day)
        return candidate
    except ValueError:
        return None


def _movie_release_reference_date(data: dict[str, Any]) -> date:
    """Use the newest extra publication date to anchor year-less release copy.

    This keeps an archived Daily Wire response stable over time. For example, a
    2026 trailer saying only ``September 16`` should still resolve to 2026 when a
    test or re-index runs in 2027.
    """
    values = data.get("movie_extras", data.get("movieExtras", [])) or []
    published_dates: list[date] = []
    for extra in values:
        published = (
            extra.published_date
            if isinstance(extra, DwMovieExtraRecord)
            else extra.get("published_date", extra.get("publishedAt"))
            if isinstance(extra, dict)
            else None
        )
        if isinstance(published, datetime):
            published_dates.append(published.date())
        elif isinstance(published, str) and published.strip():
            normalized = published.strip()
            if normalized.endswith(("Z", "z")):
                normalized = normalized[:-1] + "+00:00"
            try:
                published_dates.append(datetime.fromisoformat(normalized).date())
            except ValueError:
                pass
    return max(published_dates, default=date.today())


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

    @field_validator("published_date", mode="before")
    @classmethod
    def assume_utc_for_naive_dailywire_timestamp(cls, value: Any) -> Any:
        """Daily Wire sometimes omits the UTC suffix from movie-extra timestamps."""
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
    duration: float = 0
    sharing_url: str
    mature_rating: Optional[str] = None
    is_downloadable: bool = True
    available_for: list[str] = Field(default_factory=list)
    is_upcoming: bool = False
    expected_release_date: Optional[date] = None
    movie_extras: list[DwMovieExtraRecord] = Field(default_factory=list)
    # Kept as the dedicated trailer field consumed by the prominent movie-page
    # actions. It points to the selected trailer item in movie_extras.
    trailer: Optional[DwMovieExtraRecord] = None

    @model_validator(mode="before")
    @classmethod
    def infer_upcoming_metadata(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        explicit_upcoming = "is_upcoming" in data or "isUpcoming" in data
        explicit_release_date = (
            "expected_release_date" in data or "expectedReleaseDate" in data
        )
        raw_downloadable = data.get("is_downloadable", data.get("isDownloadable", True))
        try:
            duration = float(data.get("duration") or 0)
        except (TypeError, ValueError):
            duration = 0
        description = data.get("description")
        release_year_reference = _movie_release_reference_date(data)
        inferred_release_date = _expected_release_date(
            description,
            today=release_year_reference,
        )
        has_upcoming_copy = bool(_UPCOMING_MARKER_RE.search(str(description or "")))
        inferred_upcoming = (
            not bool(raw_downloadable)
            and has_upcoming_copy
            and (
                duration <= 0
                or (
                    inferred_release_date is not None
                    and inferred_release_date >= date.today()
                )
            )
        )

        updates: dict[str, Any] = {}
        if not explicit_upcoming:
            updates["is_upcoming"] = inferred_upcoming
        if not explicit_release_date:
            updates["expected_release_date"] = (
                inferred_release_date if inferred_upcoming else None
            )
        return {**data, **updates} if updates else data


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
