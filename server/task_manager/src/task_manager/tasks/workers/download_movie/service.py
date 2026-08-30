from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.db.models import Movie, Trailer
from backend.db.models.media_download import MediaDownloadAttempt, MediaDownloadBase
from backend.types.download_profile_types import MediaDownloadStatus
from backend.types.local_media_profile_types import LocalMediaProfileType, PreferredFormat
from backend.types.media_types import MediaType
from backend.utils.download_files import remove_download_artifacts
from backend.utils.output_template import resolve_movie_output_path
from config import get_settings
from dailywire_api.dw_api.client import MiddlewareClient
from dailywire_authorisation import DeviceAuthClient
from dailywire_downloader import (
    DownloadCancelled,
    DownloadError,
    DownloadResult,
    MediaKind,
    MediaUnavailableError,
    download_file,
    download_hls,
    probe,
    remux_to_mp4,
)
from task_manager.tasks.workers.download_attempt import DownloadAttemptGuard
from task_manager.tasks.workers.download_episode._helpers import (
    FORMAT_HEIGHTS,
    RowProgressWriter,
    select_rendition,
)

logger = logging.getLogger(__name__)


async def run_download_movie(
        session: Session,
        *,
        media_download_id: int,
        attempt_generation: Optional[int] = None,
        progress=None,
) -> None:
    download: Optional[MediaDownloadBase] = session.get(MediaDownloadBase, media_download_id)
    if download is None:
        raise DownloadCancelled(f"Media download {media_download_id} was deleted before it started")

    expected_generation = download.attempt_generation if attempt_generation is None else attempt_generation
    attempt_guard = DownloadAttemptGuard(media_download_id, expected_generation)
    attempt_guard.ensure_current()

    if download.type == MediaType.TRAILER.value:
        media = session.get(Trailer, download.media_item_id)
        if media is None:
            raise ValueError(f"Trailer {download.media_item_id} for download {media_download_id} not found")
        movie = media.movie
    else:
        media = session.get(Movie, download.media_item_id)
        if media is None:
            raise ValueError(f"Movie {download.media_item_id} for download {media_download_id} not found")
        movie = media

    profile = download.local_media_profile
    if profile.type != LocalMediaProfileType.MOVIE.value:
        raise DownloadError("Movies and trailers require a Movie Local Media Profile")
    if profile.preferred_format == PreferredFormat.FORMAT_AUDIO_ONLY.value:
        raise DownloadError("Movies and trailers require a video Local Media Profile")

    attempt_guard.update_current(
        session,
        download_status=MediaDownloadStatus.DOWNLOADING.value,
        progress=0,
        error_message=None,
        started_at=datetime.now(timezone.utc),
        finished_at=None,
    )
    session.commit()
    session.refresh(download)

    row_progress = RowProgressWriter(
        media_download_id,
        task_progress=progress,
        attempt_generation=expected_generation,
    )
    cancelled = False
    try:
        try:
            result, format_downloaded = _download_movie_media(
                session,
                movie=movie,
                media=media,
                download=download,
                row_progress=row_progress,
                attempt_guard=attempt_guard,
            )
            attempt_guard.ensure_current()
        except DownloadCancelled:
            _discard_cancelled_attempt(session, download.__dict__.get("file_path"))
            cancelled = True
            raise
        except Exception as exc:
            file_path = download.__dict__.get("file_path")
            session.rollback()
            try:
                attempt_guard.update_current(
                    session,
                    download_status=MediaDownloadStatus.ERROR.value,
                    error_message=_truncate_message(str(exc)),
                    finished_at=datetime.now(timezone.utc),
                )
            except DownloadCancelled:
                _discard_cancelled_attempt(session, file_path)
                cancelled = True
                raise
            session.refresh(download)
            _record_attempt(session, download)
            session.commit()
            raise

        try:
            attempt_guard.update_current(
                session,
                download_status=MediaDownloadStatus.DOWNLOADED.value,
                progress=100,
                downloaded_bytes=result.bytes_downloaded,
                format_downloaded=format_downloaded,
                file_path=result.path,
                finished_at=datetime.now(timezone.utc),
            )
        except DownloadCancelled:
            _discard_cancelled_attempt(session, result.path)
            cancelled = True
            raise
        media.downloaded_date = media.downloaded_date or datetime.now(timezone.utc)
        session.refresh(download)
        _record_attempt(session, download)
        session.commit()
    finally:
        if not cancelled:
            try:
                from task_manager.tasks.workers.download_profile_worker._helpers import trigger_next_pending_downloads
                trigger_next_pending_downloads(session)
            except Exception:
                logger.exception("Failed to trigger the next queued download after movie-media completion")


def _download_movie_media(
    session: Session,
    *,
    movie: Movie,
    media: Movie | Trailer,
    download: MediaDownloadBase,
    row_progress: RowProgressWriter,
    attempt_guard: DownloadAttemptGuard,
) -> tuple[DownloadResult, str]:
    attempt_guard.ensure_current()
    tokens = DeviceAuthClient().get_token()
    client = MiddlewareClient(access_token=tokens.access_token if tokens else None)
    playback = client.get_movie_playback(movie.slug)
    attempt_guard.ensure_current()

    is_trailer = isinstance(media, Trailer)
    if is_trailer:
        source_playback_url = playback.trailer_url
        if not source_playback_url:
            raise MediaUnavailableError(f"Daily Wire provides no playable video for trailer '{media.title}'")
    else:
        if not playback.has_video or not playback.video_url:
            raise MediaUnavailableError(f"Daily Wire provides no playable video for '{movie.title}'")
        source_playback_url = playback.video_url
        # Without sufficient membership Daily Wire may return the public trailer in
        # the movie endpoint. Never silently save that short fallback as the movie.
        if playback.trailer_url and source_playback_url == playback.trailer_url:
            raise MediaUnavailableError(
                f"The connected Daily Wire account does not provide access to the full movie '{movie.title}'"
            )
        if movie.duration and playback.duration and playback.duration < movie.duration * 0.5:
            raise MediaUnavailableError(
                f"Daily Wire returned only a preview for '{movie.title}', not the full movie"
            )

    info = probe(source_playback_url)
    attempt_guard.ensure_current()
    if info.kind is MediaKind.HLS_MASTER:
        requested_height = FORMAT_HEIGHTS.get(download.local_media_profile.preferred_format)
        if requested_height is None:
            raise DownloadError(
                f"Unsupported preferred format '{download.local_media_profile.preferred_format}'"
            )
        rendition = select_rendition(info.renditions, requested_height)
        source_url = rendition.url
        format_downloaded = rendition.resolution or "video"
        use_hls = True
    elif info.kind is MediaKind.HLS_MEDIA:
        source_url = source_playback_url
        format_downloaded = "video"
        use_hls = True
    else:
        source_url = source_playback_url
        format_downloaded = "video"
        use_hls = False

    remux = use_hls and get_settings().download_settings.remux_video_to_mp4
    extension = "mp4" if remux else info.suggested_extension
    destination = resolve_movie_output_path(
        download.local_media_profile.output_template,
        movie=movie,
        media_item=media,
        append_media_type_to_filename=download.local_media_profile.append_media_type_to_filename,
        extension=extension,
    )
    attempt_guard.update_current(session, file_path=str(destination))
    session.commit()
    session.refresh(download)

    if remux:
        result = _download_and_remux(source_url, str(destination), row_progress, attempt_guard)
    elif use_hls:
        result = download_hls(
            source_url,
            str(destination),
            progress=row_progress,
            should_cancel=attempt_guard,
        )
    else:
        result = download_file(
            source_url,
            str(destination),
            progress=row_progress,
            should_cancel=attempt_guard,
        )
    return result, format_downloaded


def _download_and_remux(
        source_url: str,
        destination: str,
        progress: RowProgressWriter,
        attempt_guard: DownloadAttemptGuard,
) -> DownloadResult:
    raw_path = destination + ".rawts"
    try:
        downloaded = download_hls(
            source_url,
            raw_path,
            progress=progress,
            should_cancel=attempt_guard,
        )
        attempt_guard.ensure_current()
        remux_to_mp4(
            raw_path,
            destination,
            ffmpeg_path=get_settings().download_settings.ffmpeg_path,
            should_cancel=attempt_guard,
        )
    finally:
        try:
            os.remove(raw_path)
        except OSError:
            pass
    return DownloadResult(
        path=destination,
        bytes_downloaded=downloaded.bytes_downloaded,
        segments_downloaded=downloaded.segments_downloaded,
    )


def _record_attempt(session: Session, download: MediaDownloadBase) -> None:
    session.add(MediaDownloadAttempt(
        media_download_id=download.id,
        is_redownload=False,
        status=download.download_status,
        error_message=download.error_message,
        downloaded_bytes=download.downloaded_bytes,
        format_downloaded=download.format_downloaded,
        started_at=download.started_at,
        finished_at=download.finished_at,
    ))


def _discard_cancelled_attempt(session: Session, file_path: Optional[str]) -> None:
    session.rollback()
    remove_download_artifacts(file_path)


def _truncate_message(message: str, limit: int = 20_000) -> str:
    return message if len(message) <= limit else "…" + message[-(limit - 1):]
