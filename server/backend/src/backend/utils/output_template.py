from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from .episode import episode_type_info
from config import get_settings

if TYPE_CHECKING:
    from backend.db.models import Episode, Movie, Trailer

_DOWNLOADS_PREFIX = "/downloads/"
# Characters that may not appear in a single path component
_UNSAFE_COMPONENT_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_PLACEHOLDER = re.compile(r"\{([^{}]+)}")

SHOW_OUTPUT_TEMPLATE_FIELDS = frozenset({
    "show", "show_title", "season", "season_name", "episode", "episode_title", "title",
    "episode_type", "episode_number", "ep_id", "episode_published_date", "date",
    "episode_published_time", "time", "episode_published_datetime", "datetime",
})

MOVIE_OUTPUT_TEMPLATE_FIELDS = frozenset({
    "movie", "movie_slug", "movie_title", "title", "movie_extended_title", "extended_title",
    "movie_dw_id", "dw_id", "movie_author", "author", "movie_mature_rating", "mature_rating",
    "rating", "movie_duration_seconds", "duration_seconds", "media_type",
})

# These placeholders describe the actual downloaded item rather than always describing
# the owning movie. At least one is required when the automatic trailer suffix is off.
MOVIE_MEDIA_ITEM_OUTPUT_TEMPLATE_FIELDS = frozenset({
    "title", "extended_title", "dw_id", "author", "mature_rating", "rating",
    "duration_seconds", "media_type",
})


def sanitize_path_component(value: str) -> str:
    """Make a template substitution safe to use as one path component."""
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
        "episode_published_date": episode.published_date.strftime("%Y-%m-%d") if episode.published_date else "",
        "date": episode.published_date.strftime("%Y-%m-%d") if episode.published_date else "",
        "episode_published_time": episode.published_date.strftime("%H:%M:%S") if episode.published_date else "",
        "time": episode.published_date.strftime("%H:%M:%S") if episode.published_date else "",
        "episode_published_datetime": episode.published_date.strftime("%Y-%m-%d %H:%M:%S") if episode.published_date else "",
        "datetime": episode.published_date.strftime("%Y-%m-%d %H:%M:%S") if episode.published_date else "",
    }
    return _resolve_output_path(output_template, substitutions, extension=extension)


def resolve_movie_output_path(
    output_template: str,
    *,
    movie: "Movie",
    media_item: "Movie | Trailer | None" = None,
    append_media_type_to_filename: bool = True,
    extension: Optional[str] = None,
) -> Path:
    """Resolve a Movie Local Media Profile for either its movie or one of its trailers.

    ``movie_*`` placeholders always describe ``movie``. Their generic aliases describe
    the actual downloaded media item, so for a trailer ``{title}``, ``{dw_id}``, and
    ``{duration_seconds}`` come from the trailer. ``{media_type}`` is ``movie`` or
    ``trailer``. When requested, trailers also receive a ``-trailer`` filename suffix.
    """
    validate_output_template_fields(output_template, allowed_fields=MOVIE_OUTPUT_TEMPLATE_FIELDS)

    item = media_item or movie
    is_trailer = getattr(item, "type", None) == "trailer"
    media_type = "trailer" if is_trailer else "movie"

    movie_extended_title = movie.extended_title or movie.title
    movie_duration_seconds = str(round(movie.duration or 0))

    if is_trailer:
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
    }

    resolved = output_template
    for key, value in substitutions.items():
        resolved = resolved.replace("{" + key + "}", sanitize_path_component(str(value)))

    if is_trailer and append_media_type_to_filename:
        resolved = _append_filename_suffix(resolved, "-trailer")

    return _finish_output_path(resolved, extension=extension)


def _resolve_output_path(output_template: str, substitutions: dict[str, object], *, extension: Optional[str]) -> Path:
    resolved = output_template
    for key, value in substitutions.items():
        resolved = resolved.replace("{" + key + "}", sanitize_path_component(str(value)))
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
    return (Path(get_settings().download_settings.download_root) / resolved).resolve()
