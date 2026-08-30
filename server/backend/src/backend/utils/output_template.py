from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, time
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from jinja2 import StrictUndefined, meta
from jinja2.exceptions import SecurityError, TemplateError, TemplateSyntaxError, UndefinedError
from jinja2.sandbox import ImmutableSandboxedEnvironment

from .episode import episode_type_info
from config import get_settings

if TYPE_CHECKING:
    from backend.db.models import Episode, Movie, MovieExtra

_DOWNLOADS_PREFIX = "/downloads/"
_MAX_RENDERED_PATH_LENGTH = 4096
# Characters that may not appear in a single path component.
_UNSAFE_COMPONENT_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
# Matches WireLoft's original single-brace syntax, without touching Jinja tags.
_LEGACY_PLACEHOLDER = re.compile(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*)\}(?!\})")

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

# These values describe the actual downloaded item rather than always describing
# its owning movie. They are useful when making movie and extra paths distinct.
MOVIE_MEDIA_ITEM_OUTPUT_TEMPLATE_FIELDS = frozenset({
    "title", "extended_title", "dw_id", "author", "mature_rating", "rating",
    "duration_seconds", "media_type",
})


class MovieReleaseDateUnavailableError(ValueError):
    """Deprecated: missing movie dates now render as empty values for Jinja conditions."""


def _jinja_environment() -> ImmutableSandboxedEnvironment:
    environment = ImmutableSandboxedEnvironment(
        autoescape=False,
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    # Path templates only need the explicitly supplied media values. Removing
    # globals also keeps helpers such as range() unavailable to user templates.
    environment.globals.clear()
    return environment


def upgrade_legacy_output_template(output_template: str) -> str:
    """Convert WireLoft's original ``{field}`` tokens to Jinja expressions."""
    return _LEGACY_PLACEHOLDER.sub(lambda match: "{{ " + match.group(1) + " }}", output_template)


def output_template_fields(output_template: str) -> frozenset[str]:
    """Return all context variables referenced by a Jinja path template."""
    normalized = upgrade_legacy_output_template(output_template)
    environment = _jinja_environment()
    try:
        parsed = environment.parse(normalized)
    except TemplateSyntaxError as exc:
        location = f" on line {exc.lineno}" if exc.lineno else ""
        raise ValueError(f"Invalid Jinja template{location}: {exc.message}") from exc
    return frozenset(meta.find_undeclared_variables(parsed))


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


def _sanitize_template_value(value: object, *, ascii_only: bool) -> str:
    # Empty values must stay falsey so Jinja conditionals can omit their
    # surrounding punctuation. A completely empty path component is handled
    # after rendering instead.
    text = str(value) if value is not None else ""
    if not text:
        return ""
    return sanitize_path_component(text, ascii_only=ascii_only)


def validate_output_template_fields(output_template: str, *, allowed_fields: frozenset[str]) -> str:
    """Validate Jinja syntax and reject variables unavailable for this media type."""
    normalized = upgrade_legacy_output_template(output_template)
    unsupported = sorted(output_template_fields(normalized) - allowed_fields)
    if unsupported:
        fields = ", ".join("{{ " + field + " }}" for field in unsupported)
        raise ValueError(f"Unsupported output template variable(s): {fields}")
    return normalized


def movie_template_has_media_item_field(output_template: str) -> bool:
    """Whether a movie template references a value that varies by downloaded item."""
    return bool(output_template_fields(output_template) & MOVIE_MEDIA_ITEM_OUTPUT_TEMPLATE_FIELDS)


def movie_template_uses_release_date(output_template: str) -> bool:
    """Whether a movie template references the parent movie's release date."""
    return bool(output_template_fields(output_template) & DATE_OUTPUT_TEMPLATE_FIELDS)


def episode_output_template_values(episode: "Episode") -> dict[str, str]:
    """Build the complete Show-profile context for an episode."""
    ep_info = episode_type_info(episode.episode_identifier)
    published_at = episode.published_date
    return {
        "show": episode.show.slug,
        "show_title": episode.show.title,
        "season": episode.season.slug if episode.season else "",
        "season_name": episode.season.name if episode.season else "",
        "episode": episode.slug,
        "episode_title": episode.title,
        "title": episode.title,
        "episode_type": ep_info["type"],
        "episode_number": ep_info["number"],
        "ep_id": episode.episode_identifier or "",
        "episode_published_date": published_at.strftime("%Y-%m-%d") if published_at else "",
        "episode_published_time": published_at.strftime("%H:%M:%S") if published_at else "",
        "episode_published_datetime": published_at.strftime("%Y-%m-%d %H:%M:%S") if published_at else "",
        **_date_substitutions(published_at),
    }


def movie_output_template_values(
    movie: "Movie",
    media_item: "Movie | MovieExtra | None" = None,
) -> dict[str, str]:
    """Build the complete Movie-profile context for a movie or one of its extras."""
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

    return {
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


def render_output_template(
    output_template: str,
    values: dict[str, object],
    *,
    allowed_fields: frozenset[str],
) -> str:
    """Render a path template using the same sandbox and sanitization as downloads."""
    normalized = validate_output_template_fields(output_template, allowed_fields=allowed_fields)
    ascii_only = get_settings().download_settings.ascii_only_filenames
    context = {
        field: _sanitize_template_value(values.get(field, ""), ascii_only=ascii_only)
        for field in allowed_fields
    }
    environment = _jinja_environment()
    try:
        rendered = environment.from_string(normalized).render(context)
    except (SecurityError, UndefinedError, TemplateError) as exc:
        raise ValueError(f"Could not render Jinja template: {exc}") from exc

    if "\n" in rendered or "\r" in rendered:
        raise ValueError("Rendered output path must be a single line")
    if len(rendered) > _MAX_RENDERED_PATH_LENGTH:
        raise ValueError("Rendered output path is too long")
    if not rendered.startswith(_DOWNLOADS_PREFIX):
        raise ValueError("Rendered output path must start with '/downloads/'")
    if not rendered.endswith(".ext"):
        raise ValueError("Rendered output path must end with '.ext'")
    return rendered


def resolve_episode_output_path(
    output_template: str,
    *,
    episode: "Episode",
    extension: Optional[str] = None,
) -> Path:
    rendered = render_output_template(
        output_template,
        episode_output_template_values(episode),
        allowed_fields=SHOW_OUTPUT_TEMPLATE_FIELDS,
    )
    return _finish_output_path(rendered, extension=extension)


def resolve_movie_output_path(
    output_template: str,
    *,
    movie: "Movie",
    media_item: "Movie | MovieExtra | None" = None,
    append_media_type_to_filename: bool = False,
    extension: Optional[str] = None,
) -> Path:
    """Resolve a Movie Local Media Profile for a movie or one of its extras.

    The deprecated ``append_media_type_to_filename`` argument remains for API
    compatibility. New profiles express that behavior directly in Jinja.
    """
    values = movie_output_template_values(movie, media_item)
    rendered = render_output_template(
        output_template,
        values,
        allowed_fields=MOVIE_OUTPUT_TEMPLATE_FIELDS,
    )
    if append_media_type_to_filename and values["media_type"] != "movie":
        rendered = _append_filename_suffix(rendered, f"-{values['media_type']}")
    return _finish_output_path(rendered, extension=extension)


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
        resolved = resolved[:-len("ext")] + extension.lstrip(".")

    ascii_only = get_settings().download_settings.ascii_only_filenames
    if ascii_only:
        resolved = _to_ascii(resolved)

    download_root = Path(get_settings().download_settings.download_root).resolve()
    output_path = (download_root / resolved).resolve()
    if not output_path.is_relative_to(download_root):
        raise ValueError("Rendered output path must stay inside the downloads directory")
    return output_path
