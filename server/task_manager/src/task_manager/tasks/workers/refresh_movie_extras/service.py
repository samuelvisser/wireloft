from __future__ import annotations

from sqlalchemy.orm import Session

from backend.api.endpoints.movie_extras.service import sync_movie_extras
from backend.db.models import Movie
from dailywire_api.dw_api.client import MiddlewareClient
from dailywire_authorisation import DeviceAuthClient


async def run_refresh_movie_extras(
    session: Session,
    *,
    movie_id: int,
    progress=None,
) -> int:
    movie = session.get(Movie, movie_id)
    if movie is None:
        raise ValueError(f"Movie {movie_id} was deleted before its extras could be refreshed")

    if progress is not None:
        progress.set(10, f"Fetching extras for '{movie.title}'")

    tokens = DeviceAuthClient().get_token()
    client = MiddlewareClient(access_token=tokens.access_token if tokens else None)
    movie_data = client.get_movie_page(movie.slug)

    if progress is not None:
        progress.set(65, f"Indexing {len(movie_data.movie_extras)} movie extra(s)")

    added = sync_movie_extras(
        session,
        movie=movie,
        extras=movie_data.movie_extras,
        official_trailer=movie_data.trailer,
    )
    session.commit()

    if progress is not None:
        progress.set(100, f"Added {added} new movie extra(s)")
    return added
