from __future__ import annotations

from datetime import datetime, timezone
import logging

from pydantic import ValidationError

from backend.app import db_session
from backend.db.models import Movie
from dailywire_api.dw_api.client import MiddlewareAPIError, MiddlewareClient
from dailywire_api.records import DwMovieExtraRecord, DwMovieRecord
from dailywire_authorisation import DeviceAuthClient

from ..catalog.service import get_catalog


logger = logging.getLogger(__name__)


def _aware_datetime(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _indexed_movie_fallback(movie_slug: str) -> DwMovieRecord | None:
    """Return a Daily-Wire-shaped record from WireLoft's persisted movie data.

    Once a movie has been indexed, opening its page or starting another download
    should not depend on a fresh Daily Wire metadata request. Explicit background
    refresh jobs remain responsible for fetching newer remote metadata.
    """
    with db_session() as s:
        movie = s.query(Movie).filter(Movie.slug == movie_slug).one_or_none()
        if movie is None:
            return None

        extras: list[DwMovieExtraRecord] = []
        extras_by_id: dict[int, DwMovieExtraRecord] = {}
        for extra in movie.movie_extras:
            record = DwMovieExtraRecord(
                dw_id=extra.dw_id,
                slug=extra.slug,
                title=extra.title,
                movie_extra_type=extra.movie_extra_type,
                description=extra.description,
                sharing_url=extra.sharing_url,
                published_date=_aware_datetime(extra.published_date),
                duration=float(extra.duration or 0),
                background_image_path=extra.background_image_path,
                thumbnail_landscape_path=extra.thumbnail_landscape_path,
                thumbnail_portrait_path=extra.thumbnail_portrait_path,
                thumbnail_square_path=extra.thumbnail_square_path,
            )
            extras.append(record)
            extras_by_id[extra.id] = record

        trailer = (
            extras_by_id.get(movie.official_trailer_id)
            if movie.official_trailer_id is not None
            else None
        )
        return DwMovieRecord(
            dw_id=movie.dw_id or "",
            slug=movie.slug,
            title=movie.title,
            extended_title=movie.extended_title,
            description=movie.description,
            author_name=movie.author_name,
            author_slug=movie.author_slug,
            background_image_path=movie.background_image_path,
            logo_image_path=movie.logo_image_path,
            thumbnail_landscape_path=movie.thumbnail_landscape_path,
            thumbnail_portrait_path=movie.thumbnail_portrait_path,
            thumbnail_square_path=movie.thumbnail_square_path,
            duration=float(movie.duration or 0),
            sharing_url=movie.sharing_url or f"https://www.dailywire.com/videos/{movie.slug}",
            mature_rating=movie.mature_rating,
            is_downloadable=True if movie.is_downloadable is None else bool(movie.is_downloadable),
            available_for=list(movie.available_for or []),
            movie_extras=extras,
            trailer=trailer,
        )


def _catalog_movie_fallback(movie_slug: str) -> DwMovieRecord | None:
    """Build a minimal movie detail record from the cached browse catalog.

    The catalog endpoint is independent from the movie-detail endpoint and is
    cached by WireLoft for five minutes. This fallback is intentionally only used
    to render a page; it is not authoritative enough to persist a new movie or
    start its first download because the catalog lacks detailed entitlement and
    movie-extra metadata.
    """
    summary = next(
        (movie for movie in get_catalog().movies if movie.slug == movie_slug),
        None,
    )
    if summary is None:
        return None

    return DwMovieRecord(
        **summary.model_dump(by_alias=False),
        duration=0,
        sharing_url=f"https://www.dailywire.com/videos/{movie_slug}",
        mature_rating=None,
        is_downloadable=True,
        available_for=[],
        movie_extras=[],
        trailer=None,
    )


def _live_movie(movie_slug: str) -> DwMovieRecord:
    tokens = DeviceAuthClient().get_token()
    client = MiddlewareClient(
        access_token=tokens.access_token if tokens else None,
        pace_requests=False,
    )
    return client.get_movie_page(movie_slug)


def get_movie_for_action(movie_slug: str) -> DwMovieRecord:
    """Return authoritative metadata for indexing/downloading a movie.

    Existing indexed movies use their persisted metadata and therefore need no
    upstream call. A new movie still requires the full Daily Wire detail response;
    the browse-catalog fallback is deliberately not accepted for write actions.
    """
    try:
        indexed = _indexed_movie_fallback(movie_slug)
    except Exception:
        logger.exception("Failed to read indexed movie metadata for %s", movie_slug)
    else:
        if indexed is not None:
            return indexed

    return _live_movie(movie_slug)


def get_movie(movie_slug: str) -> DwMovieRecord:
    """Return movie data for the user-facing movie page.

    Indexed movies render entirely from WireLoft's database. Non-indexed movies
    use the live Daily Wire detail endpoint, with the cached browse catalog as a
    read-only fallback when that detail endpoint returns a transient/server or
    schema error.
    """
    try:
        return get_movie_for_action(movie_slug)
    except (MiddlewareAPIError, ValidationError) as exc:
        try:
            catalog_movie = _catalog_movie_fallback(movie_slug)
        except Exception:
            logger.exception(
                "Failed to read catalog movie fallback for %s after Daily Wire detail error",
                movie_slug,
            )
        else:
            if catalog_movie is not None:
                logger.warning(
                    "Daily Wire movie detail failed for %s; serving catalog metadata instead: %s",
                    movie_slug,
                    exc,
                )
                return catalog_movie

        raise
