from __future__ import annotations

from datetime import datetime, timezone
import logging

from pydantic import ValidationError

from backend.app import db_session
from backend.db.models import Movie
from dailywire_api.dw_api.client import MiddlewareAPIError
from dailywire_api.dw_api.movie import MovieMiddlewareClient
from dailywire_api.records import DwMovieExtraRecord, DwMovieRecord
from dailywire_authorisation import DeviceAuthClient

from ..catalog.service import catalog_movie_art_is_reliable, get_catalog


logger = logging.getLogger(__name__)


def _aware_datetime(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _indexed_movie_fallback(movie_slug: str) -> DwMovieRecord | None:
    """Return a Daily-Wire-shaped record from persisted movie metadata."""
    with db_session() as s:
        movie = s.query(Movie).filter(Movie.slug == movie_slug).one_or_none()
        if movie is None:
            return None

        extras: list[DwMovieExtraRecord] = []
        extras_by_id: dict[int, DwMovieExtraRecord] = {}
        for extra in movie.movie_extras:
            record = DwMovieExtraRecord(
                dw_id=None,
                slug=extra.slug,
                title=extra.title,
                movie_extra_type=extra.movie_extra_type,
                description=extra.description,
                sharing_url=extra.sharing_url,
                published_date=_aware_datetime(extra.published_date),
                duration=float(extra.duration or 0),
                available_for=list(extra.available_for or []),
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
            # Local snapshots deliberately do not retain Daily Wire entity IDs.
            # The slug remains the canonical identity and any caller that truly
            # needs a current DW ID must resolve it from the live API by slug.
            dw_id="",
            slug=movie.slug,
            title=movie.title,
            extended_title=movie.extended_title,
            description=movie.description,
            duration=float(movie.duration or 0),
            sharing_url=movie.sharing_url or f"https://www.dailywire.com/videos/{movie.slug}",
            author_name=movie.author_name,
            author_slug=movie.author_slug,
            background_image_path=movie.background_image_path,
            logo_image_path=movie.logo_image_path,
            thumbnail_landscape_path=movie.thumbnail_landscape_path,
            thumbnail_portrait_path=movie.thumbnail_portrait_path,
            thumbnail_square_path=movie.thumbnail_square_path,
            mature_rating=movie.mature_rating,
            has_video=bool(movie.has_video),
            is_downloadable=bool(movie.is_downloadable),
            status=movie.status or "unknown",
            published_at=_aware_datetime(movie.published_at),
            background=movie.background,
            byline=movie.byline,
            language=movie.language,
            origin_country=movie.origin_country,
            images=dict(movie.images or {}),
            available_for=list(movie.available_for or []),
            cast_and_crew=list(movie.cast_and_crew or []),
            directed_by=list(movie.directed_by or []),
            genres=list(movie.genres or []),
            hosts=list(movie.hosts or []),
            production_companies=list(movie.production_companies or []),
            starring=list(movie.starring or []),
            written_by=list(movie.written_by or []),
            movie_extras=extras,
            trailer=trailer,
        )


def _catalog_movie_fallback(movie_slug: str) -> DwMovieRecord | None:
    """Build a conservative detail record from the cached browse catalog."""
    summary = next((movie for movie in get_catalog().movies if movie.slug == movie_slug), None)
    if summary is None:
        return None

    return DwMovieRecord(
        **summary.model_dump(by_alias=False),
        duration=0,
        sharing_url=f"https://www.dailywire.com/videos/{movie_slug}",
        mature_rating=None,
        has_video=False,
        is_downloadable=False,
        status="unknown",
        available_for=[],
        movie_extras=[],
        trailer=None,
    )


def _prefer_reliable_catalog_poster(movie: DwMovieRecord) -> DwMovieRecord:
    """Use the browse poster when that row is already the real movie representation.

    getMoviePage remains authoritative for all other movie artwork and metadata.
    Daily Wire can, however, expose the better portrait poster in the browse
    catalog. Promotional browse rows are excluded with the same reliability rule
    used by the Browse page itself.
    """
    try:
        summary = next(
            (item for item in get_catalog().movies if item.slug == movie.slug),
            None,
        )
    except Exception as exc:
        logger.warning(
            "Daily Wire catalog poster lookup failed for movie %s; keeping movie-page poster: %s",
            movie.slug,
            exc,
        )
        return movie

    if summary is None or not catalog_movie_art_is_reliable(summary):
        return movie

    return movie.model_copy(update={"thumbnail_portrait_path": summary.thumbnail_portrait_path})


def get_live_movie(movie_slug: str) -> DwMovieRecord:
    """Fetch current movie metadata and normalize its poster for persistence."""
    tokens = DeviceAuthClient().get_token()
    client = MovieMiddlewareClient(
        access_token=tokens.access_token if tokens else None,
        pace_requests=False,
    )
    movie = client.get_movie_page(movie_slug)
    return _prefer_reliable_catalog_poster(movie)


def get_movie_for_action(movie_slug: str) -> DwMovieRecord:
    """Return authoritative metadata for indexing/downloading a movie.

    Scheduled or otherwise unavailable indexed movies are refreshed live so their
    release transition is discovered. Released downloadable movies may use the
    persisted canonical movie-page snapshot for low-latency actions.
    """
    indexed: DwMovieRecord | None = None
    try:
        indexed = _indexed_movie_fallback(movie_slug)
    except Exception:
        logger.exception("Failed to read indexed movie metadata for %s", movie_slug)

    if indexed is not None and indexed.status == "published" and indexed.is_downloadable:
        return indexed

    try:
        return get_live_movie(movie_slug)
    except (MiddlewareAPIError, ValidationError) as exc:
        if indexed is not None:
            logger.warning(
                "Daily Wire movie detail failed for indexed movie %s; serving persisted metadata instead: %s",
                movie_slug,
                exc,
            )
            return indexed
        raise


def get_movie(movie_slug: str) -> DwMovieRecord:
    """Return movie data for the user-facing movie page."""
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
