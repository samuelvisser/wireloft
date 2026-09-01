from __future__ import annotations

from collections.abc import Sequence
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.api.models.movie_extra import MovieExtraAPICreate, MovieExtraAPIRead
from backend.db.models import Movie, MovieExtra
from backend.types.media_types import MovieExtraType
from backend.utils.helpers import generate_uuid
from dailywire_api.records import DwMovieExtraRecord


def create_movie_extra(
    s: Session,
    movie_id: int,
    body: MovieExtraAPICreate,
) -> MovieExtraAPIRead:
    """Create a movie extra owned by a movie without committing the transaction."""
    movie = s.get(Movie, movie_id)
    if movie is None:
        raise HTTPException(status_code=404, detail="Movie not found")

    item = MovieExtra(movie=movie, **body.model_dump(by_alias=True))
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
    """Upsert the extras exposed by Daily Wire and return the number added.

    Slugs are the playback identifiers and are therefore the primary matching
    key. A non-empty Daily Wire ID is also accepted so a later slug change
    updates the existing logical extra instead of creating a duplicate.
    """
    existing = list(movie.movie_extras)
    by_slug = {extra.slug: extra for extra in existing}
    by_dw_id = {extra.dw_id: extra for extra in existing if extra.dw_id}
    added = 0

    for record in extras:
        item = by_dw_id.get(record.dw_id) if record.dw_id else None
        item = item or by_slug.get(record.slug)
        if item is None:
            item = MovieExtra(
                movie=movie,
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
                movie_extra_type=record.movie_extra_type,
                dw_id=record.dw_id,
                slug=record.slug,
                sharing_url=record.sharing_url,
                published_date=record.published_date,
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
            item.movie_extra_type = record.movie_extra_type
            item.dw_id = record.dw_id
            item.slug = record.slug
            item.sharing_url = record.sharing_url
            item.published_date = record.published_date

        by_slug[item.slug] = item
        if item.dw_id:
            by_dw_id[item.dw_id] = item

    s.flush()

    if official_trailer is None:
        movie.official_trailer = None
    else:
        official = by_dw_id.get(official_trailer.dw_id) if official_trailer.dw_id else None
        official = official or by_slug.get(official_trailer.slug)
        if official is None or official.movie_id != movie.id:
            raise ValueError("The official trailer is not present in this movie's extras")
        if official.movie_extra_type != MovieExtraType.TRAILER.value:
            raise ValueError("The official trailer extra is not classified as a trailer")
        movie.official_trailer = official

    s.flush()
    return added
