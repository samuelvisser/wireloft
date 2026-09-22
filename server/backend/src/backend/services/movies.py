from __future__ import annotations

from collections.abc import Sequence
from typing import Optional

from sqlalchemy.orm import Session

from backend.db.model_mapping import create_database_fields, update_database_fields
from backend.db.models import Movie, MovieExtra, MovieExtraSource
from backend.integrations.tmdb import MovieReleaseLookupResult, lookup_movie_release_metadata
from backend.types.media_types import MediaType, MovieExtraType
from backend.utils.helpers import generate_uuid
from dailywire_api.records import DwMovieExtraRecord, DwMovieRecord


DAILYWIRE_RELEASE_SOURCE = "dailywire"
_DAILYWIRE_MOVIE_FIELDS = {
    "title",
    "description",
    "duration",
    "background_image_path",
    "thumbnail_landscape_path",
    "thumbnail_portrait_path",
    "thumbnail_square_path",
    "extended_title",
    "sharing_url",
    "author_name",
    "author_slug",
    "logo_image_path",
    "mature_rating",
    "has_video",
    "is_downloadable",
    "status",
    "published_at",
    "background",
    "byline",
    "language",
    "origin_country",
    "images",
    "available_for",
    "cast_and_crew",
    "directed_by",
    "genres",
    "hosts",
    "production_companies",
    "starring",
    "written_by",
}


def _movie_extra_persistent_values(record: DwMovieExtraRecord) -> dict:
    """Project one upstream extra onto MovieExtra's persisted flat domain contract."""
    values = record.model_dump(mode="python", by_alias=False)
    source_fields = {
        column.key
        for column in MovieExtraSource.__table__.columns
        if column.key != "id"
    }
    return {
        field: values[field]
        for field in source_fields
        if field in values
    }




def apply_movie_release_lookup(item: Movie, lookup: MovieReleaseLookupResult) -> None:
    item.release_date = lookup.release_date
    item.release_date_source = lookup.source
    item.release_date_source_id = lookup.source_id
    item.release_date_lookup_status = lookup.status
    item.release_date_lookup_attempted_at = lookup.attempted_at
    item.release_date_lookup_error = lookup.error


def ensure_movie_release_metadata(s: Session, item: Movie) -> None:
    """Run at most one TMDB lookup when The Daily Wire supplied no release instant."""
    if item.release_date_source == DAILYWIRE_RELEASE_SOURCE:
        return
    if item.release_date_lookup_attempted_at is not None:
        return

    lookup = lookup_movie_release_metadata(
        title=item.title,
        description=item.description,
        duration_seconds=item.duration,
    )
    if lookup is None:
        return

    apply_movie_release_lookup(item, lookup)
    s.flush()


def update_movie_extra_source_metadata(
    source: MovieExtraSource,
    metadata: DwMovieExtraRecord,
) -> None:
    if metadata.slug != source.slug:
        raise ValueError("MovieExtraSource metadata can only be updated for the same slug")

    values = metadata.model_dump(
        mode="python",
        by_alias=False,
        exclude_unset=True,
    )
    for column in MovieExtraSource.__table__.columns:
        field = column.key
        if field in {"id", "slug"} or field not in values:
            continue
        setattr(source, field, values[field])


def sync_movie_extras(
    s: Session,
    *,
    movie: Movie,
    extras: Sequence[DwMovieExtraRecord],
    official_trailer: Optional[DwMovieExtraRecord],
) -> int:
    """Upsert one movie's extra placements from canonical Daily Wire records."""
    existing = list(movie.movie_extras)
    by_slug = {extra.slug: extra for extra in existing}
    official_trailer_slug = official_trailer.slug if official_trailer is not None else None
    added = 0

    for record in extras:
        values = _movie_extra_persistent_values(record)
        movie_extra_type = (
            MovieExtraType.TRAILER.value
            if record.slug == official_trailer_slug
            else record.movie_extra_type
        )
        item = by_slug.get(record.slug)

        if item is None:
            item = MovieExtra(
                movie=movie,
                uuid=generate_uuid(),
                type=MediaType.MOVIE_EXTRA.value,
                movie_extra_type=movie_extra_type,
                **values,
            )
            s.add(item)
            existing.append(item)
            added += 1
        else:
            # Sparse parent representations must not erase richer source data.
            update_database_fields(
                item,
                {
                    field: value
                    for field, value in values.items()
                    if value is not None
                    and not (
                        isinstance(value, (str, list, dict))
                        and not value
                    )
                    and not (field == "duration" and value <= 0)
                },
                ignore_extra_fields=True,
            )
            item.movie_extra_type = movie_extra_type

        by_slug[record.slug] = item

    s.flush()

    if official_trailer is None:
        movie.official_trailer = None
    else:
        official = by_slug.get(official_trailer.slug)
        if official is None or official.movie_id != movie.id:
            raise ValueError("The official trailer is not present in this movie's extras")
        official.movie_extra_type = MovieExtraType.TRAILER.value
        movie.official_trailer = official

    s.flush()
    return added


def sync_dailywire_movie_metadata(
    s: Session,
    *,
    movie: Movie,
    movie_data: DwMovieRecord,
) -> None:
    """Refresh canonical movie metadata without persisting rotating Daily Wire IDs."""
    values = movie_data.model_dump(mode="python", by_alias=False)
    update_database_fields(
        movie,
        {field: values[field] for field in _DAILYWIRE_MOVIE_FIELDS if field in values},
    )

    if movie_data.published_at is not None:
        movie.release_date = movie_data.published_at.date()
        movie.release_date_source = DAILYWIRE_RELEASE_SOURCE
        movie.release_date_source_id = None
        movie.release_date_lookup_status = "matched"
        movie.release_date_lookup_attempted_at = None
        movie.release_date_lookup_error = None

    s.flush()


def sync_indexed_dailywire_movie(
    s: Session,
    *,
    movie: Movie,
    movie_data: DwMovieRecord,
) -> None:
    sync_dailywire_movie_metadata(s, movie=movie, movie_data=movie_data)
    sync_movie_extras(
        s,
        movie=movie,
        extras=movie_data.movie_extras,
        official_trailer=movie_data.trailer,
    )
    if movie.release_date is None:
        ensure_movie_release_metadata(s, movie)


def index_dailywire_movie(
    s: Session,
    movie_data: DwMovieRecord,
) -> tuple[Movie, bool]:
    """Persist a Daily Wire movie by stable slug and all currently known extras."""
    item = s.query(Movie).filter(Movie.slug == movie_data.slug).one_or_none()
    created = item is None
    if item is None:
        values = movie_data.model_dump(mode="python", by_alias=False)
        item = create_database_fields(
            Movie,
            values,
            exclude_fields={"id", "movie_extras", "trailer"},
        )
        item.uuid = generate_uuid()
        item.type = MediaType.MOVIE.value
        s.add(item)
        s.flush()

    sync_indexed_dailywire_movie(s, movie=item, movie_data=movie_data)
    return item, created
