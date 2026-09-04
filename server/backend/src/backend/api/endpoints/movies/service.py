from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.api.helpers import update_database_fields
from backend.api.models.movie import *
from backend.api.models.movie_extra import MovieExtraAPICreate
from backend.db.models.media_download import MediaDownloadBase
from backend.db.models.media_item import Movie
from backend.api.endpoints.movie_extras.service import create_movie_extra, sync_movie_extras
from backend.integrations.tmdb import MovieReleaseLookupResult, lookup_movie_release_metadata
from dailywire_api.records import DwMovieRecord
from task_manager.scheduler.operations import (
    OperationTargetSpec,
    create_operation,
    queue_operation_target_dispatch,
)


_REFRESH_MOVIE_EXTRAS_TASK_KEY = "refresh_movie_extras"


def get_movies_list(s: Session) -> list[MovieAPIRead]:
    items = (
        s.query(Movie)
        .order_by(Movie.title.asc())
        .all()
    )
    return [MovieAPIRead.model_validate(it) for it in items]


def get_movie(s: Session, movie_slug: str) -> MovieAPIRead:
    item = (
        s.query(Movie)
        .filter(Movie.slug == movie_slug)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Movie not found")

    return MovieAPIRead.model_validate(item)


def request_movie_extras_refresh(s: Session, movie_slug: str) -> dict[str, bool | str]:
    """Queue a UI-visible movie-extra refresh through the TaskOperation pipeline."""
    movie: Optional[Movie] = (
        s.query(Movie)
        .filter(Movie.slug == movie_slug)
        .one_or_none()
    )
    if movie is None:
        raise HTTPException(status_code=404, detail="Movie not found")

    target = OperationTargetSpec(
        task_key=_REFRESH_MOVIE_EXTRAS_TASK_KEY,
        resource_type="movie",
        resource_id=movie.id,
    )
    operation = create_operation(
        s,
        kind="movie.refresh_extras",
        resource_type="movie",
        resource_id=movie.id,
        title=movie.title,
        targets=[target],
        context={
            "movie_slug": movie.slug,
            "movie_title": movie.title,
        },
    )
    queue_operation_target_dispatch(
        s,
        operation.id,
        target.resolved_slot_key(),
    )
    return {"queued": True, "operation_id": operation.id}


def _apply_movie_release_lookup(item: Movie, lookup: MovieReleaseLookupResult) -> None:
    item.release_date = lookup.release_date
    item.release_date_source = lookup.source
    item.release_date_source_id = lookup.source_id
    item.release_date_lookup_status = lookup.status
    item.release_date_lookup_attempted_at = lookup.attempted_at
    item.release_date_lookup_error = lookup.error


def ensure_movie_release_metadata(s: Session, item: Movie) -> None:
    """Run at most one configured release-date lookup for a persisted movie."""
    if item.release_date_lookup_attempted_at is not None:
        return

    lookup = lookup_movie_release_metadata(
        title=item.title,
        description=item.description,
        duration_seconds=item.duration,
    )
    # A missing token is not counted as an attempt. This lets a movie that was
    # indexed before TMDB was configured receive its one lookup the next time
    # a download path indexes it.
    if lookup is None:
        return

    _apply_movie_release_lookup(item, lookup)
    s.flush()


def retry_movie_release_metadata(s: Session, movie_slug: str) -> MovieAPIRead:
    """Retry a transient TMDB lookup failure for an already-persisted movie."""
    item: Optional[Movie] = (
        s.query(Movie)
        .filter(Movie.slug == movie_slug)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Movie not found")
    if item.release_date_lookup_status != "error":
        raise HTTPException(
            status_code=409,
            detail="TMDB release metadata can only be retried after a lookup error",
        )

    lookup = lookup_movie_release_metadata(
        title=item.title,
        description=item.description,
        duration_seconds=item.duration,
    )
    if lookup is None:
        raise HTTPException(
            status_code=422,
            detail="Configure a TMDB API Read Access Token before retrying movie release metadata",
        )

    _apply_movie_release_lookup(item, lookup)
    s.flush()
    return MovieAPIRead.model_validate(item)


def create_movie(s: Session, body: MovieAPICreate) -> MovieAPIRead:
    data = body.model_dump(
        by_alias=True,
        exclude={"movie_extras", "official_trailer_slug"},
    )
    item = Movie(**data)
    s.add(item)
    s.flush()

    for movie_extra in body.movie_extras:
        create_movie_extra(s, item.id, movie_extra)

    if body.official_trailer_slug is not None:
        official_trailer = next(
            (
                extra
                for extra in item.movie_extras
                if extra.slug == body.official_trailer_slug
            ),
            None,
        )
        if official_trailer is None:
            raise ValueError("The official trailer must be included in movie_extras")
        item.official_trailer = official_trailer
        s.flush()

    # Movie, extras and any calling operation remain in the caller's single
    # transaction. Services flush only; routers own commit and rollback. The
    # Daily Wire browser indexing performs release metadata enrichment in
    # index_dailywire_movie, not for arbitrary direct API-created movies.
    return MovieAPIRead.model_validate(item)


def index_dailywire_movie(s: Session, movie_data: DwMovieRecord) -> tuple[Movie, bool]:
    """Persist a Daily Wire movie and all currently known extras without downloading it."""
    item: Optional[Movie] = (
        s.query(Movie)
        .filter(Movie.slug == movie_data.slug)
        .one_or_none()
    )
    created = item is None
    if item is None:
        result = create_movie(s, _movie_create_from_dailywire(movie_data))
        item = s.get(Movie, result.id)
        if item is None:
            raise RuntimeError("Movie creation did not produce a persisted Movie record")

    # Keep this idempotent so the explicit Add action and every direct download
    # path also pick up extras that appeared since the movie was first indexed.
    sync_movie_extras(
        s,
        movie=item,
        extras=movie_data.movie_extras,
        official_trailer=movie_data.trailer,
    )

    if item.release_date_lookup_attempted_at is None:
        ensure_movie_release_metadata(s, item)
    return item, created


def _movie_create_from_dailywire(movie_data: DwMovieRecord) -> MovieAPICreate:
    movie_extras = [
        MovieExtraAPICreate(
            dw_id=extra.dw_id,
            slug=extra.slug,
            title=extra.title,
            movie_extra_type=extra.movie_extra_type,
            published_date=extra.published_date,
            description=extra.description,
            sharing_url=extra.sharing_url,
            duration=extra.duration,
            background_image_path=extra.background_image_path,
            thumbnail_landscape_path=extra.thumbnail_landscape_path,
            thumbnail_portrait_path=extra.thumbnail_portrait_path,
            thumbnail_square_path=extra.thumbnail_square_path,
        )
        for extra in movie_data.movie_extras
    ]

    return MovieAPICreate(
        dw_id=movie_data.dw_id,
        slug=movie_data.slug,
        title=movie_data.title,
        extended_title=movie_data.extended_title,
        description=movie_data.description,
        duration=movie_data.duration,
        background_image_path=movie_data.background_image_path,
        thumbnail_landscape_path=movie_data.thumbnail_landscape_path,
        thumbnail_portrait_path=movie_data.thumbnail_portrait_path,
        thumbnail_square_path=movie_data.thumbnail_square_path,
        sharing_url=movie_data.sharing_url,
        author_name=movie_data.author_name,
        author_slug=movie_data.author_slug,
        logo_image_path=movie_data.logo_image_path,
        mature_rating=movie_data.mature_rating,
        is_downloadable=movie_data.is_downloadable,
        available_for=movie_data.available_for,
        movie_extras=movie_extras,
        official_trailer_slug=(movie_data.trailer.slug if movie_data.trailer else None),
    )


def update_movie(s: Session, movie_slug: str, body: MovieAPIUpdate) -> MovieAPIRead:
    item: Optional[Movie] = (
        s.query(Movie)
        .filter(Movie.slug == movie_slug)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Movie not found")

    update_database_fields(item, body)
    s.flush()
    return MovieAPIRead.model_validate(item)


def delete_movie(s: Session, movie_slug: str) -> MovieAPIRead:
    item = (
        s.query(Movie)
        .filter(Movie.slug == movie_slug)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Movie not found")

    payload = MovieAPIRead.model_validate(item)

    # Route every Movie and MovieExtra download through the normal deletion
    # service before removing their media records. Active downloads are thereby
    # cancelled and their partial artifacts removed, while completed files are
    # deliberately left on disk.
    media_item_ids = [item.id, *(extra.id for extra in item.movie_extras)]
    download_ids = list(s.scalars(
        select(MediaDownloadBase.id).where(
            MediaDownloadBase.media_item_id.in_(media_item_ids),
        )
    ))
    from backend.api.endpoints.media_downloads.service import delete_media_download
    for download_id in download_ids:
        delete_media_download(s, download_id)

    s.delete(item)
    s.flush()
    return payload
