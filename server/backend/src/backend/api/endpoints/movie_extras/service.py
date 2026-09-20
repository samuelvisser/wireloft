from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.api.models.movie_extra import (
    MovieExtraAPICreate,
    MovieExtraAPIRead,
)
from backend.db.models import Movie, MovieExtra
from backend.types.media_types import MediaType
from backend.services.movies import sync_movie_extras, update_movie_extra_source_metadata


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


