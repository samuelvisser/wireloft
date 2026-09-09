from __future__ import annotations

import logging
from threading import Lock
from time import monotonic

from pydantic import ValidationError

from dailywire_api.dw_api.client import MiddlewareAPIError, MiddlewareClient
from dailywire_api.dw_api.movie import MovieMiddlewareClient
from dailywire_api.records import (
    DwCatalogMoviePageRecord,
    DwCatalogMovieRecord,
    DwCatalogRecord,
    DwCatalogShowPageRecord,
)
from dailywire_authorisation import DeviceAuthClient


logger = logging.getLogger(__name__)

_CATALOG_CACHE_SECONDS = 5 * 60
_catalog_cache: tuple[float, DwCatalogRecord] | None = None
_catalog_lock = Lock()


def get_catalog() -> DwCatalogRecord:
    """Return a short-lived local snapshot of the Daily Wire catalog."""
    global _catalog_cache

    now = monotonic()
    with _catalog_lock:
        if _catalog_cache and now - _catalog_cache[0] < _CATALOG_CACHE_SECONDS:
            return _catalog_cache[1]

        tokens = DeviceAuthClient().get_token()
        client = MiddlewareClient(
            access_token=tokens.access_token if tokens else None,
            pace_requests=False,
        )
        catalog = client.get_catalog()
        _catalog_cache = (monotonic(), catalog)
        return catalog


def _matches_search(title: str, author_name: str | None, search: str | None) -> bool:
    needle = (search or '').strip().casefold()
    return not needle or needle in f"{title} {author_name or ''}".casefold()


def catalog_movie_art_is_reliable(movie: DwCatalogMovieRecord) -> bool:
    """Whether a browse row already contains the movie's real artwork.

    Daily Wire sometimes represents an unreleased movie with its currently
    promoted trailer. Those rows may omit a portrait entirely or carry a trailer
    title/artwork even though the canonical getMoviePage record has the real
    movie poster. If the catalog has a portrait and its upstream title did not
    need normalization, its artwork is the preferred movie-card artwork.
    """
    extended_title = (movie.extended_title or '').strip()
    return bool(movie.thumbnail_portrait_path) and not (
        extended_title and extended_title != movie.title
    )


def _canonical_movie_summary(
    movie: DwCatalogMovieRecord,
    client: MovieMiddlewareClient,
) -> DwCatalogMovieRecord:
    """Overlay only artwork from the canonical v4/getMoviePage record.

    Search, ordering, and pagination are based on the browse catalog, so keep its
    identity/text metadata intact and use the detail endpoint solely to correct
    artwork that may describe a promoted trailer rather than the movie itself.
    """
    try:
        detail = client.get_movie_page(movie.slug)
    except (MiddlewareAPIError, ValidationError) as exc:
        logger.warning(
            "Daily Wire movie-page metadata failed for catalog movie %s; keeping browse artwork: %s",
            movie.slug,
            exc,
        )
        return movie

    artwork_fields = (
        "background_image_path",
        "logo_image_path",
        "thumbnail_landscape_path",
        "thumbnail_portrait_path",
        "thumbnail_square_path",
    )
    updates = {
        field_name: value
        for field_name in artwork_fields
        if (value := getattr(detail, field_name, None))
    }
    return movie.model_copy(update=updates) if updates else movie


def get_catalog_shows(
    *, offset: int, limit: int, search: str | None, grouping: str,
) -> DwCatalogShowPageRecord:
    shows = [
        show for show in get_catalog().shows
        if _matches_search(show.title, show.author_name, search)
    ]
    if grouping == 'host':
        shows.sort(key=lambda show: ((show.author_name or 'Other').casefold(), show.title.casefold()))
    else:
        shows.sort(key=lambda show: show.title.casefold())

    items = shows[offset:offset + limit]
    return DwCatalogShowPageRecord(
        items=items,
        offset=offset,
        limit=limit,
        total=len(shows),
        has_more=offset + len(items) < len(shows),
    )


def get_catalog_movies(*, offset: int, limit: int, search: str | None) -> DwCatalogMoviePageRecord:
    movies = [
        movie for movie in get_catalog().movies
        if _matches_search(movie.title, movie.author_name, search)
    ]
    movies.sort(key=lambda movie: movie.title.casefold())

    items = movies[offset:offset + limit]
    if any(not catalog_movie_art_is_reliable(movie) for movie in items):
        tokens = DeviceAuthClient().get_token()
        client = MovieMiddlewareClient(
            access_token=tokens.access_token if tokens else None,
            pace_requests=False,
        )
        items = [
            _canonical_movie_summary(movie, client)
            if not catalog_movie_art_is_reliable(movie)
            else movie
            for movie in items
        ]

    return DwCatalogMoviePageRecord(
        items=items,
        offset=offset,
        limit=limit,
        total=len(movies),
        has_more=offset + len(items) < len(movies),
    )
