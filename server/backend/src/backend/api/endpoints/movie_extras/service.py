from __future__ import annotations

from collections.abc import Sequence
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.api.models.movie_extra import MovieExtraAPICreate, MovieExtraAPIRead
from backend.db.models import Movie, MovieExtra, MovieExtraSource
from backend.types.media_types import MediaType, MovieExtraType
from backend.utils.helpers import generate_uuid
from dailywire_api.records import DwMovieExtraRecord


def get_or_create_movie_extra_source(s: Session, slug: str) -> MovieExtraSource:
    """Resolve the one global source row for an immutable Daily Wire clip slug.

    The unique slug constraint is the final authority. A nested transaction keeps
    the caller's larger indexing/download transaction usable if two workers race
    to discover the same source for different parent movies.
    """
    source = s.scalar(select(MovieExtraSource).where(MovieExtraSource.slug == slug))
    if source is not None:
        return source

    try:
        with s.begin_nested():
            source = MovieExtraSource(slug=slug)
            s.add(source)
            s.flush()
    except IntegrityError:
        source = s.scalar(select(MovieExtraSource).where(MovieExtraSource.slug == slug))
        if source is None:
            raise
    return source


def _apply_source_metadata(
    source: MovieExtraSource,
    record: MovieExtraAPICreate | DwMovieExtraRecord,
) -> None:
    """Merge the best known globally intrinsic metadata into one clip source.

    A shared clip can be listed on multiple movie pages and one page may omit a
    field that another includes. Non-empty values therefore refresh the source,
    while an omitted value never erases richer metadata learned elsewhere.
    """
    if record.title:
        source.title = record.title
    if record.description:
        source.description = record.description
    if record.duration > 0 or (source.duration or 0) <= 0:
        source.duration = record.duration

    for field in (
        "background_image_path",
        "thumbnail_landscape_path",
        "thumbnail_portrait_path",
        "thumbnail_square_path",
        "sharing_url",
    ):
        value = getattr(record, field)
        if value:
            setattr(source, field, value)

    if record.published_date is not None:
        source.published_date = record.published_date
    if record.available_for:
        source.available_for = list(record.available_for)


def create_movie_extra(
    s: Session,
    movie_id: int,
    body: MovieExtraAPICreate,
) -> MovieExtraAPIRead:
    """Create a movie-specific placement while sharing canonical clip metadata."""
    movie = s.get(Movie, movie_id)
    if movie is None:
        raise HTTPException(status_code=404, detail="Movie not found")

    source = get_or_create_movie_extra_source(s, body.slug)
    _apply_source_metadata(source, body)
    item = MovieExtra(
        movie=movie,
        source=source,
        uuid=body.uuid,
        type=MediaType.MOVIE_EXTRA.value,
        movie_extra_type=body.movie_extra_type,
    )
    s.add(item)
    s.flush()
    return MovieExtraAPIRead.model_validate(item)


def sync_movie_extras(
    s: Session,
    *,
    movie: Movie,
    extras: Sequence[DwMovieExtraRecord],
    official_trailer: Optional[DwMovieExtraRecord],
) -> int:
    """Upsert one movie's placements and one canonical source per clip slug.

    Daily Wire entity IDs are intentionally ignored because they can rotate over
    time. ``MovieExtraSource`` owns the immutable slug and every globally
    intrinsic metadata field. ``MovieExtra`` stores only placement-specific state
    such as the parent movie and classification. It remains a MediaItem so the
    existing one-download-per-media-item-and-profile invariant stays unchanged.

    The dedicated ``official_trailer`` relationship is more authoritative than
    the inferred extra type. Older WireLoft versions could persist a trailer as
    ``scene`` or ``other``, so syncing repairs that per-movie classification.
    """
    existing = list(movie.movie_extras)
    by_slug = {extra.slug: extra for extra in existing}
    official_trailer_slug = official_trailer.slug if official_trailer is not None else None
    added = 0

    for record in extras:
        source = get_or_create_movie_extra_source(s, record.slug)
        _apply_source_metadata(source, record)

        item = by_slug.get(record.slug)
        movie_extra_type = (
            MovieExtraType.TRAILER.value
            if record.slug == official_trailer_slug
            else record.movie_extra_type
        )
        if item is None:
            item = MovieExtra(
                movie=movie,
                source=source,
                uuid=generate_uuid(),
                type=MediaType.MOVIE_EXTRA.value,
                movie_extra_type=movie_extra_type,
            )
            s.add(item)
            existing.append(item)
            added += 1
        else:
            # The slug lookup and source uniqueness guarantee this is normally
            # already the same object. Reassigning makes legacy/inconsistent rows
            # self-heal instead of carrying a second source identity forward.
            item.source = source
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
