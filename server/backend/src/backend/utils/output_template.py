from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from .episode import episode_type_info
from config import get_settings

if TYPE_CHECKING:
    from backend.db.models import Episode, Movie

_DOWNLOADS_PREFIX = "/downloads/"
# Characters that may not appear in a single path component
_UNSAFE_COMPONENT_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_PLACEHOLDER = re.compile(r"\{([^{}]+)}")

SHOW_OUTPUT_TEMPLATE_FIELDS = frozenset({
    "show",
    "show_title",
    "season",
    "season_name",
    "episode",
    "episode_title",
    "title",
    "episode_type",
    "episode_number",
    "ep_id",
    "episode_published_date",
    "date",
    "episode_published_time",
    "time",
    "episode_published_datetime",
    "datetime",
})

MOVIE_OUTPUT_TEMPLATE_FIELDS = frozenset({
    "movie",
    "movie_slug",
    "movie_title",
    "title",
    "movie_extended_title",
    "extended_title",
    "movie_dw_id",
    "dw_id",
    "movie_author",
    "author",
    "movie_mature_rating",
    "mature_rating",
    "rating",
    "movie_duration_seconds",
    "duration_seconds",
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


def resolve_episode_output_path(
        output_template: str,
        *,
        episode: "Episode",
        extension: Optional[str] = None,
) -> Path:
    """Resolve a Local Media Profile output template to an absolute file path.

    Supported placeholders: ``{show}``/``{show_title}``, ``{season}``/``{season_name}``,
    ``{episode}``/``{episode_title}``/``{title}`` and ``{ep_id}``. The mandatory
    ``/downloads/`` prefix maps to the configured ``download_settings.download_root``
    directory, and the mandatory ``.ext`` suffix is replaced with the actual file
    extension once it is known.
    """

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

    resolved = output_template
    for key, value in substitutions.items():
        resolved = resolved.replace("{" + key + "}", sanitize_path_component(str(value)))

    if resolved.startswith(_DOWNLOADS_PREFIX):
        resolved = resolved[len(_DOWNLOADS_PREFIX):]
    resolved = resolved.lstrip("/")

    if extension is not None and resolved.endswith(".ext"):
        resolved = resolved[: -len("ext")] + extension.lstrip(".")

    root = Path(get_settings().download_settings.download_root)
    return (root / resolved).resolve()


def resolve_movie_output_path(
    output_template: str,
    *,
    movie: "Movie",
    extension: Optional[str] = None,
) -> Path:
    """Resolve a Movie Local Media Profile template for a one-off movie."""
    validate_output_template_fields(output_template, allowed_fields=MOVIE_OUTPUT_TEMPLATE_FIELDS)

    extended_title = movie.extended_title or movie.title
    duration_seconds = str(round(movie.duration or 0))
    substitutions = {
        "movie": movie.slug,
        "movie_slug": movie.slug,
        "movie_title": movie.title,
        "title": movie.title,
        "movie_extended_title": extended_title,
        "extended_title": extended_title,
        "movie_dw_id": movie.dw_id or "",
        "dw_id": movie.dw_id or "",
        "movie_author": movie.author_name or "",
        "author": movie.author_name or "",
        "movie_mature_rating": movie.mature_rating or "",
        "mature_rating": movie.mature_rating or "",
        "rating": movie.mature_rating or "",
        "movie_duration_seconds": duration_seconds,
        "duration_seconds": duration_seconds,
    }

    resolved = output_template
    for key, value in substitutions.items():
        resolved = resolved.replace("{" + key + "}", sanitize_path_component(str(value)))

    if resolved.startswith(_DOWNLOADS_PREFIX):
        resolved = resolved[len(_DOWNLOADS_PREFIX):]
    resolved = resolved.lstrip("/")
    if extension is not None and resolved.endswith(".ext"):
        resolved = resolved[: -len("ext")] + extension.lstrip(".")

    return (Path(get_settings().download_settings.download_root) / resolved).resolve()
