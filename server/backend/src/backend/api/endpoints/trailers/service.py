from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.api.models.trailer import TrailerAPICreate, TrailerAPIRead
from backend.db.models import Movie, Trailer


def create_trailer(
    s: Session,
    movie_id: int,
    body: TrailerAPICreate,
) -> TrailerAPIRead:
    """Create a trailer owned by a movie without committing the transaction."""
    if s.get(Movie, movie_id) is None:
        raise HTTPException(status_code=404, detail="Movie not found")

    data = body.model_dump(by_alias=True)
    item = Trailer(movie_id=movie_id, **data)
    s.add(item)
    s.flush()
    return TrailerAPIRead.model_validate(item)
