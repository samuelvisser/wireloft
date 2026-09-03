from __future__ import annotations

from threading import Lock
from time import monotonic

from dailywire_api.dw_api.client import MiddlewareClient
from dailywire_api.records import (
    DwCatalogMoviePageRecord,
    DwCatalogRecord,
    DwCatalogShowPageRecord,
)
from dailywire_authorisation import DeviceAuthClient


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
    return DwCatalogMoviePageRecord(
        items=items,
        offset=offset,
        limit=limit,
        total=len(movies),
        has_more=offset + len(items) < len(movies),
    )
