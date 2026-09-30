from __future__ import annotations

from datetime import date, datetime
from typing import Iterable

from backend.db.models.media_item import Episode
from backend.types.show_types import EpisodeIdentifier
from dailywire_downloader.metadata import MediaServerMetadata


def build_episode_metadata(episode: Episode, show) -> MediaServerMetadata:
    published = episode.published_date or episode.went_live_date or episode.scheduled_date
    season_number: int | None = None
    episode_number: int | None = None
    if show.episode_identifier != EpisodeIdentifier.DATE_BASED.value:
        season = getattr(episode, "season", None)
        raw_season = getattr(season, "season_number", None)
        if isinstance(raw_season, int):
            season_number = raw_season
        raw_episode = getattr(episode, "episode_number", None)
        if raw_episode is not None and str(raw_episode).isdigit():
            episode_number = int(raw_episode)

    return MediaServerMetadata(
        kind="episode",
        title=episode.title,
        description=episode.description,
        unique_id=episode.slug or episode.uuid,
        source_url=episode.sharing_url,
        show_title=show.title,
        season_number=season_number,
        episode_index=episode.index,
        episode_number=episode_number,
        aired=_as_date(published),
        duration_seconds=episode.duration,
        authors=_strings((show.author_name,)),
        studios=("The Daily Wire",),
        media_type="episode",
    )


def build_movie_metadata(movie, media) -> MediaServerMetadata:
    is_extra = media is not movie
    release_date = _as_date(
        getattr(media, "published_date", None)
        if is_extra
        else movie.release_date or movie.published_at
    )
    genres = _named_values(movie.genres)
    directors = _named_values(movie.directed_by)
    writers = _named_values(movie.written_by)
    cast = _named_values(movie.starring) or _named_values(movie.cast_and_crew)
    studios = _named_values(movie.production_companies) or ("The Daily Wire",)

    return MediaServerMetadata(
        kind="movie_extra" if is_extra else "movie",
        title=media.title,
        description=media.description,
        unique_id=getattr(media, "slug", None) or getattr(media, "uuid", None),
        source_url=getattr(media, "sharing_url", None) or movie.sharing_url,
        release_date=release_date,
        duration_seconds=media.duration,
        authors=_strings((movie.author_name,)),
        genres=genres,
        directors=directors,
        writers=writers,
        cast=cast,
        studios=studios,
        language=movie.language,
        country=movie.origin_country,
        content_rating=movie.mature_rating,
        parent_movie_title=movie.title if is_extra else None,
        media_type=getattr(media, "movie_extra_type", None) if is_extra else "movie",
    )


def _as_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    return value if isinstance(value, date) else None


def _strings(values: Iterable[object] | object | None) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        values = (values,)
    elif not isinstance(values, Iterable):
        values = (values,)
    result = []
    for value in values:
        if isinstance(value, str) and value.strip():
            result.append(value.strip())
    return tuple(dict.fromkeys(result))


def _named_values(values: Iterable[object] | object | None) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        return _strings(values)
    if isinstance(values, dict):
        direct = next(
            (
                str(values[key]).strip()
                for key in ("name", "title", "label")
                if values.get(key)
            ),
            "",
        )
        if direct:
            return (direct,)
        flattened: list[str] = []
        for nested in values.values():
            flattened.extend(_named_values(nested))
        return tuple(dict.fromkeys(flattened))
    if not isinstance(values, Iterable):
        return ()

    names: list[str] = []
    for value in values:
        names.extend(_named_values(value))
    return tuple(dict.fromkeys(names))




def select_thumbnail_url(media) -> str | None:
    """Choose the best artwork source for embedding or a per-media sidecar."""
    for attribute in (
        "thumbnail_square_path",
        "thumbnail_portrait_path",
        "thumbnail_landscape_path",
        "background_image_path",
    ):
        value = getattr(media, attribute, None)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
    return None
