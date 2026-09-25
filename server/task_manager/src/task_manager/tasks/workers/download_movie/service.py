from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.api.endpoints.movie_extras.service import update_movie_extra_source_metadata
from backend.db.models import Movie, MovieExtra
from backend.db.models.media_download import MediaDownloadBase
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from backend.types.media_download_history_types import MediaDownloadHistoryAction
from backend.types.local_media_profile_types import LocalMediaProfileType, PreferredFormat
from backend.types.media_types import MediaType
from backend.services.media_download_history import (
    download_attempt_metadata,
    record_media_download_history,
    record_media_download_history_if_exists,
)
from backend.utils.artifact_identity import inspect_artifact
from backend.utils.output_template import resolve_movie_output_path
from config import get_settings
from dailywire_api.dw_api.movie import MovieMiddlewareClient
from dailywire_api.records import DwMovieExtraRecord
from dailywire_authorisation import DeviceAuthClient
from dailywire_downloader import DownloadCancelled, DownloadError, MediaUnavailableError
from task_manager.scheduler.operation_context import current_operation_ids
from task_manager.scheduler.results import TaskResult
from task_manager.tasks.helpers.downloads.download_files import remove_download_artifacts
from task_manager.tasks.helpers.downloads.download_modes import (
    effective_download_mode,
    effective_thumbnail_mode,
)
from task_manager.tasks.helpers.downloads.engine import (
    DownloadExecution,
    DownloadPlan,
    TaskProgressWriter,
    ensure_not_cancelled,
    execute_download_plan,
    resolve_download_source,
)
from task_manager.tasks.helpers.downloads.thumbnails import select_thumbnail_url


@dataclass(frozen=True)
class _MovieExtraPlaybackResolution:
    source_url: str
    metadata: DwMovieExtraRecord | None


async def run_download_movie(
    session: Session,
    *,
    media_download_id: int,
    is_redownload: bool = False,
    progress=None,
) -> TaskResult:
    """Produce one movie/movie-extra artifact; TaskRun owns execution state."""
    download: Optional[MediaDownloadBase] = session.get(MediaDownloadBase, media_download_id)
    if download is None:
        raise DownloadCancelled(f"Media download {media_download_id} was deleted before it started")

    if download.type == MediaType.MOVIE_EXTRA.value:
        media = session.get(MovieExtra, download.media_item_id)
        if media is None:
            raise ValueError(
                f"Movie extra {download.media_item_id} for download {media_download_id} not found"
            )
        movie = media.movie
    else:
        media = session.get(Movie, download.media_item_id)
        if media is None:
            raise ValueError(
                f"Movie {download.media_item_id} for download {media_download_id} not found"
            )
        movie = media

    profile = download.local_media_profile
    if profile.type != LocalMediaProfileType.MOVIE.value:
        raise DownloadError("Movies and movie extras require a Movie Local Media Profile")
    if profile.preferred_format in {
        PreferredFormat.FORMAT_AUDIO_ONLY.value,
        PreferredFormat.FORMAT_HLS.value,
    }:
        raise DownloadError(
            "Movies and movie extras require a normal video Local Media Profile"
        )

    if progress is not None:
        progress.set(0, f"Starting download for {media.title}")
    task_progress = TaskProgressWriter(progress)
    execution: DownloadExecution | None = None
    attempt_started_at = datetime.now(timezone.utc)
    operation_ids = current_operation_ids()
    operation_metadata = {"operation_ids": list(operation_ids)} if operation_ids else {}
    record_media_download_history(
        session,
        media_download_id,
        MediaDownloadHistoryAction.STARTED,
        metadata={
            "is_redownload": bool(is_redownload),
            **operation_metadata,
        },
        occurred_at=attempt_started_at,
    )
    session.commit()

    try:
        ensure_not_cancelled(progress)
        execution = _download_movie_media(
            session,
            movie=movie,
            media=media,
            download=download,
            task_progress=task_progress,
            cancellation=progress,
        )
        ensure_not_cancelled(progress)

        session.rollback()
        session.expire_all()
        download = session.get(MediaDownloadBase, media_download_id)
        if download is None:
            remove_download_artifacts(execution.result.path, execution.thumbnail_path)
            raise DownloadCancelled("Media download was deleted while the worker was running")
        ensure_not_cancelled(progress)

        artifact_identity = inspect_artifact(execution.result.path)
        download.file_path = execution.result.path
        download.thumbnail_path = execution.thumbnail_path
        download.artifact_stat_dev = artifact_identity.stat_dev
        download.artifact_stat_ino = artifact_identity.stat_ino
        download.artifact_size_bytes = artifact_identity.size_bytes
        download.artifact_fingerprint = artifact_identity.fingerprint
        download.artifact_status = MediaDownloadArtifactStatus.AVAILABLE.value
        download.artifact_error = None
        download.automatic_retry_suppressed = False
        download.downloaded_bytes = execution.result.bytes_downloaded
        download.format_downloaded = execution.format_downloaded
        finished_at = datetime.now(timezone.utc)
        download.downloaded_at = finished_at

        media = session.get(
            MovieExtra if download.type == MediaType.MOVIE_EXTRA.value else Movie,
            download.media_item_id,
        )
        record_media_download_history(
            session,
            media_download_id,
            MediaDownloadHistoryAction.COMPLETED,
            metadata=download_attempt_metadata(
                started_at=attempt_started_at,
                finished_at=finished_at,
                is_redownload=is_redownload,
                **operation_metadata,
                downloaded_bytes=execution.result.bytes_downloaded,
                format_downloaded=execution.format_downloaded,
                file_path=execution.result.path,
                thumbnail_path=execution.thumbnail_path,
            ),
            occurred_at=finished_at,
        )
        session.commit()

        return TaskResult(
            summary=f"Downloaded {getattr(media, 'title', movie.title)}",
            data={
                "media_download_id": media_download_id,
                "downloaded_bytes": execution.result.bytes_downloaded,
                "format_downloaded": execution.format_downloaded,
                "file_path": execution.result.path,
                "thumbnail_path": execution.thumbnail_path,
                "is_redownload": is_redownload,
            },
        )
    except DownloadCancelled as exc:
        session.rollback()
        if execution is not None:
            remove_download_artifacts(execution.result.path, execution.thumbnail_path)
        finished_at = datetime.now(timezone.utc)
        if record_media_download_history_if_exists(
            session,
            media_download_id,
            MediaDownloadHistoryAction.CANCELLED,
            metadata=download_attempt_metadata(
                started_at=attempt_started_at,
                finished_at=finished_at,
                is_redownload=is_redownload,
                **operation_metadata,
                reason=str(exc) or "Canceled",
            ),
            occurred_at=finished_at,
        ) is not None:
            session.commit()
        raise
    except Exception as exc:
        session.rollback()
        if execution is not None:
            remove_download_artifacts(execution.result.path, execution.thumbnail_path)
        finished_at = datetime.now(timezone.utc)
        if record_media_download_history_if_exists(
            session,
            media_download_id,
            MediaDownloadHistoryAction.FAILED,
            metadata=download_attempt_metadata(
                started_at=attempt_started_at,
                finished_at=finished_at,
                is_redownload=is_redownload,
                **operation_metadata,
                error=exc,
            ),
            occurred_at=finished_at,
        ) is not None:
            session.commit()
        raise
    finally:
        if execution is not None:
            execution.cleanup_workspace()


def _download_movie_media(
    session: Session,
    *,
    movie: Movie,
    media: Movie | MovieExtra,
    download: MediaDownloadBase,
    task_progress: TaskProgressWriter,
    cancellation,
) -> DownloadExecution:
    ensure_not_cancelled(cancellation)

    is_extra = isinstance(media, MovieExtra)
    download_id = download.id
    movie_id = movie.id
    media_id = media.id
    movie_slug = movie.slug
    movie_title = movie.title
    movie_duration = movie.duration
    official_trailer_id = movie.official_trailer_id
    extra_slug = media.slug if is_extra else None
    extra_title = media.title if is_extra else None
    profile = download.local_media_profile
    preferred_format = profile.preferred_format
    output_template = profile.output_template
    download_mode = effective_download_mode(profile)
    thumbnail_mode = effective_thumbnail_mode(profile)
    thumbnail_url = select_thumbnail_url(media)
    settings = get_settings().download_settings

    # Authentication, playback lookup and probing may all block on the internet.
    # Snapshot the required local values and release the transaction first.
    session.rollback()
    tokens = DeviceAuthClient().get_token()
    client = MovieMiddlewareClient(access_token=tokens.access_token if tokens else None)
    if is_extra:
        resolution = _resolve_movie_extra_playback(
            client,
            movie_slug=movie_slug,
            official_trailer_id=official_trailer_id,
            extra_id=media_id,
            extra_slug=extra_slug,
            extra_title=extra_title,
        )
        ensure_not_cancelled(cancellation)
        source_playback_url = resolution.source_url
        if resolution.metadata is not None:
            thumbnail_refreshed, fresh_thumbnail_url = _persist_movie_extra_metadata(
                session,
                extra_id=media_id,
                metadata=resolution.metadata,
            )
            if thumbnail_refreshed:
                thumbnail_url = fresh_thumbnail_url
    else:
        playback = client.get_movie_playback(movie_slug)
        ensure_not_cancelled(cancellation)
        if not playback.has_video or not playback.video_url:
            raise MediaUnavailableError(
                f"Daily Wire provides no playable video for '{movie_title}'"
            )
        source_playback_url = playback.video_url
        if playback.trailer_url and source_playback_url == playback.trailer_url:
            raise MediaUnavailableError(
                f"The connected Daily Wire account does not provide access to the full movie '{movie_title}'"
            )
        if movie_duration and playback.duration and playback.duration < movie_duration * 0.5:
            raise MediaUnavailableError(
                f"Daily Wire returned only a preview for '{movie_title}', not the full movie"
            )

    source = resolve_download_source(
        source_playback_url,
        preferred_format=preferred_format,
        audio_only=False,
        remux_video_to_mp4=settings.remux_video_to_mp4,
        cancellation=cancellation,
    )
    task_progress.set_selected_format(source.format_downloaded)

    # Re-enter the DB only after all pre-download network discovery is complete.
    download = session.get(MediaDownloadBase, download_id)
    movie = session.get(Movie, movie_id)
    media = session.get(MovieExtra if is_extra else Movie, media_id)
    if download is None or movie is None or media is None:
        raise DownloadCancelled("Movie download resources were deleted while resolving playback")

    requested_destination = resolve_movie_output_path(
        output_template,
        movie=movie,
        media_item=media,
        extension=source.extension,
    )

    # Resolving the destination needs ORM-backed movie metadata. Release that
    # transaction again before the potentially long media transfer.
    session.rollback()

    plan = DownloadPlan(
        source=source,
        requested_destination=requested_destination,
        download_mode=download_mode,
        temporary_root=settings.temporary_download_root,
        ffmpeg_path=settings.ffmpeg_path,
        thumbnail_url=thumbnail_url,
        thumbnail_mode=thumbnail_mode,
    )

    def persist_direct_destination(destination: str) -> None:
        download.file_path = destination
        session.commit()

    return execute_download_plan(
        plan,
        task_progress=task_progress,
        cancellation=cancellation,
        on_direct_destination_reserved=persist_direct_destination,
    )


def _persist_movie_extra_metadata(
    session: Session,
    *,
    extra_id: int,
    metadata: DwMovieExtraRecord,
) -> tuple[bool, str | None]:
    """Persist metadata already returned by ``getClip`` and release the transaction."""
    extra = session.get(MovieExtra, extra_id)
    if extra is None:
        raise DownloadCancelled("Movie extra was deleted while resolving playback")

    update_movie_extra_source_metadata(extra.source, metadata)

    thumbnail_fields = {
        "thumbnail_landscape_path",
        "thumbnail_portrait_path",
        "thumbnail_square_path",
        "background_image_path",
    }
    thumbnail_refreshed = bool(metadata.model_fields_set & thumbnail_fields)
    thumbnail_url = select_thumbnail_url(metadata) if thumbnail_refreshed else None
    session.commit()
    return thumbnail_refreshed, thumbnail_url


def _resolve_movie_extra_playback(
    client: MovieMiddlewareClient,
    *,
    movie_slug: str,
    official_trailer_id: int | None,
    extra_id: int,
    extra_slug: str | None,
    extra_title: str | None,
) -> _MovieExtraPlaybackResolution:
    if not extra_slug:
        raise MediaUnavailableError(f"Movie extra {extra_id} has no Daily Wire slug")

    metadata: DwMovieExtraRecord | None = None
    try:
        playback = client.get_movie_extra_playback(extra_slug)
        source_url = playback.video_url
        playback_metadata = getattr(playback, "metadata", None)
        if isinstance(playback_metadata, DwMovieExtraRecord):
            metadata = playback_metadata
    except Exception:
        if official_trailer_id != extra_id:
            raise
        source_url = None

    if not source_url and official_trailer_id == extra_id:
        movie_page = client.get_movie_page(movie_slug)
        source_url = movie_page.trailer.trailer_url if movie_page.trailer else None
    if not source_url:
        raise MediaUnavailableError(
            f"Daily Wire provides no playable video for movie extra '{extra_title or extra_slug}'"
        )
    return _MovieExtraPlaybackResolution(source_url=source_url, metadata=metadata)


def _movie_extra_playback_url(
    client: MovieMiddlewareClient,
    *,
    movie_slug: str,
    official_trailer_id: int | None,
    extra_id: int,
    extra_slug: str | None,
    extra_title: str | None,
) -> str:
    return _resolve_movie_extra_playback(
        client,
        movie_slug=movie_slug,
        official_trailer_id=official_trailer_id,
        extra_id=extra_id,
        extra_slug=extra_slug,
        extra_title=extra_title,
    ).source_url
