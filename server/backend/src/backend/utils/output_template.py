from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, time
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from .episode import episode_type_info
from config import get_settings

if TYPE_CHECKING:
    from backend.db.models import Episode, Movie, MovieExtra

_DOWNLOADS_PREFIX = "/downloads/"
# Characters that may not appear in a single path component
_UNSAFE_COMPONENT_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_PLACEHOLDER = re.compile(r"\{([^{}]+)}")

DATE_OUTPUT_TEMPLATE_FIELDS = frozenset({
    "date", "time", "datetime", "year", "month", "day", "hour", "minute", "second",
})

SHOW_OUTPUT_TEMPLATE_FIELDS = frozenset({
    "show", "show_title", "season", "season_name", "episode", "episode_title", "title",
    "episode_type", "episode_number", "ep_id", "episode_published_date",
    "episode_published_time", "episode_published_datetime",
}) | DATE_OUTPUT_TEMPLATE_FIELDS

MOVIE_OUTPUT_TEMPLATE_FIELDS = frozenset({
    "movie", "movie_slug", "movie_title", "title", "movie_extended_title", "extended_title",
    "movie_dw_id", "dw_id", "movie_author", "author", "movie_mature_rating", "mature_rating",
    "rating", "movie_duration_seconds", "duration_seconds", "media_type",
}) | DATE_OUTPUT_TEMPLATE_FIELDS

# These placeholders describe the actual downloaded item rather than always describing
# the owning movie. At least one is required when the automatic extra suffix is off.
MOVIE_MEDIA_ITEM_OUTPUT_TEMPLATE_FIELDS = frozenset({
    "title", "extended_title", "dw_id", "author", "mature_rating", "rating",
    "duration_seconds", "media_type",
})


class MovieReleaseDateUnavailableError(ValueError):
    """Raised when a movie template needs release metadata that is unavailable."""


def _to_ascii(value: str) -> str:
    """Transliterate decomposable Unicode characters and drop remaining non-ASCII characters."""
    normalized = unicodedata.normalize("NFKD", value)
    return normalized.encode("ascii", "ignore").decode("ascii")


def sanitize_path_component(value: str, *, ascii_only: bool = False) -> str:
    """Make a template substitution safe to use as one path component."""
    if ascii_only:
        value = _to_ascii(value)
    cleaned = _UNSAFE_COMPONENT_CHARS.sub("_", value).strip(" .")
    return cleaned or "_"


def validate_output_template_fields(output_template: str, *, allowed_fields: frozenset[str]) -> str:
    """Reject placeholders that cannot be resolved for a profile's media type."""
    unsupported = sorted(set(_PLACEHOLDER.findall(output_template)) - allowed_fields)
    if unsupported:
        fields = ", ".join("{" + field + "}" for field in unsupported)
        raise ValueError(f"Unsupported output template placeholder(s): {fields}")
    return output_template


def movie_template_has_media_item_field(output_template: str) -> bool:
    """Whether a movie template contains a field that varies with the downloaded item."""
    return bool(set(_PLACEHOLDER.findall(output_template)) & MOVIE_MEDIA_ITEM_OUTPUT_TEMPLATE_FIELDS)


def movie_template_uses_release_date(output_template: str) -> bool:
    """Whether a movie template needs the parent movie's canonical release date."""
    return bool(set(_PLACEHOLDER.findall(output_template)) & DATE_OUTPUT_TEMPLATE_FIELDS)


def resolve_episode_output_path(
        output_template: str,
        *,
        episode: "Episode",
        extension: Optional[str] = None,
) -> Path:
    validate_output_template_fields(output_template, allowed_fields=SHOW_OUTPUT_TEMPLATE_FIELDS)

    ep_info = episode_type_info(episode.episode_identifier)
    ep_type = ep_info["type"]
    ep_number = ep_info["number"]
    published_at = episode.published_date
    substitutions = {
        "show": episode.show.slug,
        "show_title": episode.show.title,
        "season": episode.season.slug if episode.season else "",
        "season_name": episode.season.name if episode.season else "",
        "episode": episode.slug,
        "episode_title": episode.title,
        "title": episode.title,
        "episode_type": ep_type,
        "episode_number": ep_number,
        "ep_id": episode.episode_identifier or "",
        "episode_published_date": published_at.strftime("%Y-%m-%d") if published_at else "",
        "episode_published_time": published_at.strftime("%H:%M:%S") if published_at else "",
        "episode_published_datetime": published_at.strftime("%Y-%m-%d %H:%M:%S") if published_at else "",
        **_date_substitutions(published_at),
    }
    return _resolve_output_path(output_template, substitutions, extension=extension)


def resolve_movie_output_path(
    output_template: str,
    *,
    movie: "Movie",
    media_item: "Movie | MovieExtra | None" = None,
    append_media_type_to_filename: bool = True,
    extension: Optional[str] = None,
) -> Path:
    """Resolve a Movie Local Media Profile for a movie or one of its extras.

    ``movie_*`` placeholders always describe ``movie``. Their generic aliases describe
    the actual downloaded media item, so for an extra ``{title}``, ``{dw_id}``, and
    ``{duration_seconds}`` come from the extra. Date/time placeholders always describe
    the parent movie's canonical release date. TMDB supplies a date rather than a time,
    so movie time components resolve to midnight. ``{media_type}`` is ``movie`` or
    the extra's ``movie_extra_type``. When requested, extras also receive a matching
    filename suffix such as ``-trailer`` or ``-interview``.
    """
    validate_output_template_fields(output_template, allowed_fields=MOVIE_OUTPUT_TEMPLATE_FIELDS)

    if movie_template_uses_release_date(output_template) and movie.release_date is None:
        status = getattr(movie, "release_date_lookup_status", None) or "pending"
        lookup_error = getattr(movie, "release_date_lookup_error", None)
        detail = f" Lookup status: {status}."
        if lookup_error:
            detail += f" {lookup_error}"
        if status == "pending":
            guidance = (
                "Configure a TMDB API Read Access Token, restart WireLoft so the setting is "
                "reloaded, and try this movie or movie-extra download again."
            )
        else:
            guidance = (
                "The one-time lookup has already completed. Use an output template without "
                "date/time placeholders for this movie, or correct its stored release metadata."
            )
        raise MovieReleaseDateUnavailableError(
            "This Movie Local Media Profile uses release-date placeholders, but WireLoft "
            f"has no canonical release date stored for '{movie.title}'.{detail} {guidance}"
        )

    item = media_item or movie
    is_movie_extra = getattr(item, "type", None) == "movie_extra"
    media_type = getattr(item, "movie_extra_type", "other") if is_movie_extra else "movie"

    movie_extended_title = movie.extended_title or movie.title
    movie_duration_seconds = str(round(movie.duration or 0))

    if is_movie_extra:
        item_title = item.title
        item_extended_title = item.title
        item_dw_id = getattr(item, "dw_id", None) or ""
        item_author = ""
        item_rating = ""
        item_duration_seconds = str(round(item.duration or 0))
    else:
        item_title = movie.title
        item_extended_title = movie_extended_title
        item_dw_id = movie.dw_id or ""
        item_author = movie.author_name or ""
        item_rating = movie.mature_rating or ""
        item_duration_seconds = movie_duration_seconds

    substitutions = {
        "movie": movie.slug,
        "movie_slug": movie.slug,
        "movie_title": movie.title,
        "title": item_title,
        "movie_extended_title": movie_extended_title,
        "extended_title": item_extended_title,
        "movie_dw_id": movie.dw_id or "",
        "dw_id": item_dw_id,
        "movie_author": movie.author_name or "",
        "author": item_author,
        "movie_mature_rating": movie.mature_rating or "",
        "mature_rating": item_rating,
        "rating": item_rating,
        "movie_duration_seconds": movie_duration_seconds,
        "duration_seconds": item_duration_seconds,
        "media_type": media_type,
        **_date_substitutions(getattr(movie, "release_date", None)),
    }

    ascii_only = get_settings().download_settings.ascii_only_filenames
    resolved = output_template
    for key, value in substitutions.items():
        resolved = resolved.replace(
            "{" + key + "}",
            sanitize_path_component(str(value), ascii_only=ascii_only),
        )

    if ascii_only:
        resolved = _to_ascii(resolved)

    if is_movie_extra and append_media_type_to_filename:
        resolved = _append_filename_suffix(resolved, f"-{media_type}")

    return _finish_output_path(resolved, extension=extension)


def _date_substitutions(value: Optional[date | datetime]) -> dict[str, str]:
    if value is None:
        return {field: "" for field in DATE_OUTPUT_TEMPLATE_FIELDS}
    if isinstance(value, datetime):
        value_datetime = value
    else:
        value_datetime = datetime.combine(value, time.min)
    return {
        "date": value_datetime.strftime("%Y-%m-%d"),
        "time": value_datetime.strftime("%H:%M:%S"),
        "datetime": value_datetime.strftime("%Y-%m-%d %H:%M:%S"),
        "year": value_datetime.strftime("%Y"),
        "month": value_datetime.strftime("%m"),
        "day": value_datetime.strftime("%d"),
        "hour": value_datetime.strftime("%H"),
        "minute": value_datetime.strftime("%M"),
        "second": value_datetime.strftime("%S"),
    }


def _resolve_output_path(output_template: str, substitutions: dict[str, object], *, extension: Optional[str]) -> Path:
    ascii_only = get_settings().download_settings.ascii_only_filenames
    resolved = output_template
    for key, value in substitutions.items():
        resolved = resolved.replace(
            "{" + key + "}",
            sanitize_path_component(str(value), ascii_only=ascii_only),
        )
    return _finish_output_path(resolved, extension=extension)


def _append_filename_suffix(path: str, suffix: str) -> str:
    if path.endswith(".ext"):
        return path[:-4] + suffix + ".ext"
    file_path = Path(path)
    return str(file_path.with_name(file_path.stem + suffix + file_path.suffix))


def _finish_output_path(resolved: str, *, extension: Optional[str]) -> Path:
    if resolved.startswith(_DOWNLOADS_PREFIX):
        resolved = resolved[len(_DOWNLOADS_PREFIX):]
    resolved = resolved.lstrip("/")
    if extension is not None and resolved.endswith(".ext"):
        resolved = resolved[: -len("ext")] + extension.lstrip(".")

    # Handle ASCII-only
    ascii_only = get_settings().download_settings.ascii_only_filenames
    if ascii_only:
        resolved = _to_ascii(resolved)

    return (Path(get_settings().download_settings.download_root) / resolved).resolve()
