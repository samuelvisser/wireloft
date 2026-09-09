from __future__ import annotations

from collections.abc import Sequence
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.api.models.movie_extra import MovieExtraAPICreate, MovieExtraAPIRead
from backend.db.models import Movie, MovieExtra, MovieExtraSource
from backend.types.media_types import MovieExtraType
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


def create_movie_extra(
    s: Session,
    movie_id: int,
    body: MovieExtraAPICreate,
) -> MovieExtraAPIRead:
    """Create a movie-specific extra listing without committing the transaction."""
    movie = s.get(Movie, movie_id)
    if movie is None:
        raise HTTPException(status_code=404, detail="Movie not found")

    data = body.model_dump(by_alias=True)
    source = get_or_create_movie_extra_source(s, data.pop("slug"))
    item = MovieExtra(movie=movie, source=source, **data)
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
    """Upsert one movie's extra listings while sharing global clip identity.

    Daily Wire entity IDs are intentionally ignored because they can rotate over
    time. ``MovieExtraSource`` owns the immutable clip slug globally, while each
    ``MovieExtra`` remains a separate MediaItem placement under one parent movie.
    That distinction lets the same source appear under multiple movies without
    changing WireLoft's one-download-per-media-item-and-profile invariant.

    The dedicated ``official_trailer`` relationship is more authoritative than
    the inferred extra type. Older WireLoft versions could persist a trailer as
    ``scene`` or ``other`` (for example when Daily Wire described it generically
    as a clip), so syncing repairs that classification instead of rejecting the
    entire movie and blocking every extra download.
    """
    existing = list(movie.movie_extras)
    by_slug = {extra.slug: extra for extra in existing}
    official_trailer_slug = official_trailer.slug if official_trailer is not None else None
    added = 0

    for record in extras:
        item = by_slug.get(record.slug)
        movie_extra_type = (
            MovieExtraType.TRAILER.value
            if record.slug == official_trailer_slug
            else record.movie_extra_type
        )
        if item is None:
            source = get_or_create_movie_extra_source(s, record.slug)
            item = MovieExtra(
                movie=movie,
                source=source,
                uuid=generate_uuid(),
                type="movie_extra",
                title=record.title,
                description=record.description,
                downloaded_date=None,
                duration=record.duration,
                background_image_path=record.background_image_path,
                thumbnail_landscape_path=record.thumbnail_landscape_path,
                thumbnail_portrait_path=record.thumbnail_portrait_path,
                thumbnail_square_path=record.thumbnail_square_path,
                movie_extra_type=movie_extra_type,
                sharing_url=record.sharing_url,
                published_date=record.published_date,
                available_for=list(record.available_for),
            )
            s.add(item)
            existing.append(item)
            added += 1
        else:
            item.title = record.title
            item.description = record.description
            item.duration = record.duration
            item.background_image_path = record.background_image_path
            item.thumbnail_landscape_path = record.thumbnail_landscape_path
            item.thumbnail_portrait_path = record.thumbnail_portrait_path
            item.thumbnail_square_path = record.thumbnail_square_path
            item.movie_extra_type = movie_extra_type
            item.sharing_url = record.sharing_url
            item.published_date = record.published_date
            item.available_for = list(record.available_for)

        by_slug[item.slug] = item

    s.flush()

    if official_trailer is None:
        movie.official_trailer = None
    else:
        official = by_slug.get(official_trailer.slug)
        if official is None or official.movie_id != movie.id:
            raise ValueError("The official trailer is not present in this movie's extras")
        # The API's dedicated trailer relationship is canonical. This also
        # self-heals legacy rows that were persisted with an inferred type.
        official.movie_extra_type = MovieExtraType.TRAILER.value
        movie.official_trailer = official

    s.flush()
    return added
