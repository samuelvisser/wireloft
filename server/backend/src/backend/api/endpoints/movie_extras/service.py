from __future__ import annotations

from collections.abc import Sequence
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.api.helpers import update_database_fields
from backend.api.models.movie_extra import (
    MovieExtraAPICreate,
    MovieExtraAPIRead,
    MovieExtraAPIUpdate,
)
from backend.db.models import Movie, MovieExtra
from backend.types.media_types import MediaType, MovieExtraType
from backend.utils.helpers import generate_uuid
from dailywire_api.records import DwMovieExtraRecord


def create_movie_extra(
    s: Session,
    movie_id: int,
    body: MovieExtraAPICreate,
) -> MovieExtraAPIRead:
    """Create a movie-specific extra without exposing source normalization."""
    movie = s.get(Movie, movie_id)
    if movie is None:
        raise HTTPException(status_code=404, detail="Movie not found")

    item = MovieExtra(
        movie=movie,
        type=MediaType.MOVIE_EXTRA.value,
        **body.model_dump(by_alias=True),
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
    """Upsert one movie's extra placements by stable source slug.

    ``MovieExtra`` owns source resolution. Callers interact only with the flat
    MovieExtra attributes; constructing a new placement transparently reuses or
    creates the canonical MovieExtraSource during flush.
    """
    existing = list(movie.movie_extras)
    by_slug = {extra.slug: extra for extra in existing}
    official_trailer_slug = official_trailer.slug if official_trailer is not None else None
    added = 0

    for record in extras:
        update = MovieExtraAPIUpdate.model_validate(record)
        movie_extra_type = (
            MovieExtraType.TRAILER.value
            if record.slug == official_trailer_slug
            else record.movie_extra_type
        )
        item = by_slug.get(record.slug)

        if item is None:
            values = update.model_dump(by_alias=True)
            values["movie_extra_type"] = movie_extra_type
            item = MovieExtra(
                movie=movie,
                uuid=generate_uuid(),
                type=MediaType.MOVIE_EXTRA.value,
                **values,
            )
            s.add(item)
            existing.append(item)
            added += 1
        else:
            # Sparse metadata from one parent must not erase richer global
            # metadata learned from another parent for the same source clip.
            update_database_fields(
                item,
                update,
                exclude_none=True,
                exclude_defaults=True,
            )
            item.movie_extra_type = movie_extra_type

        by_slug[record.slug] = item

    # Flush resolves any newly constructed placements onto their canonical source
    # rows before the official-trailer relationship is finalized.
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
