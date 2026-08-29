from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.db.models import Movie
from backend.db.models.media_download import MediaDownloadAttempt, MediaDownloadBase
from backend.types.download_profile_types import MediaDownloadStatus
from backend.types.local_media_profile_types import PreferredFormat
from backend.utils.output_template import resolve_movie_output_path
from config import get_settings
from dailywire_api.dw_api.client import MiddlewareClient
from dailywire_authorisation import DeviceAuthClient
from dailywire_downloader import (
    DownloadError,
    DownloadResult,
    MediaKind,
    MediaUnavailableError,
    download_file,
    download_hls,
    probe,
    remux_to_mp4,
)
from task_manager.tasks.workers.download_episode._helpers import (
    FORMAT_HEIGHTS,
    RowProgressWriter,
    select_rendition,
)

logger = logging.getLogger(__name__)


async def run_download_movie(session: Session, *, media_download_id: int, progress=None) -> None:
    download: Optional[MediaDownloadBase] = session.get(MediaDownloadBase, media_download_id)
    if download is None:
        raise ValueError(f"Media download {media_download_id} not found")
    movie: Optional[Movie] = session.get(Movie, download.media_item_id)
    if movie is None:
        raise ValueError(f"Movie {download.media_item_id} for download {media_download_id} not found")
    profile = download.local_media_profile
    if profile.preferred_format == PreferredFormat.FORMAT_AUDIO_ONLY.value:
        raise DownloadError("Movies require a video Local Media Profile")

    download.download_status = MediaDownloadStatus.DOWNLOADING.value
    download.progress = 0
    download.error_message = None
    download.started_at = datetime.now(timezone.utc)
    download.finished_at = None
    session.commit()

    row_progress = RowProgressWriter(media_download_id, task_progress=progress)
    try:
        try:
            result, format_downloaded = _download_movie_media(
                session,
                movie=movie,
                download=download,
                row_progress=row_progress,
            )
        except Exception as exc:
            session.rollback()
            download.download_status = MediaDownloadStatus.ERROR.value
            download.error_message = _truncate_message(str(exc))
            download.finished_at = datetime.now(timezone.utc)
            _record_attempt(session, download)
            session.commit()
            raise

        download.download_status = MediaDownloadStatus.DOWNLOADED.value
        download.progress = 100
        download.downloaded_bytes = result.bytes_downloaded
        download.format_downloaded = format_downloaded
        download.file_path = result.path
        download.finished_at = datetime.now(timezone.utc)
        movie.downloaded_date = movie.downloaded_date or datetime.now(timezone.utc)
        _record_attempt(session, download)
        session.commit()
    finally:
        try:
            from task_manager.tasks.workers.download_profile_worker._helpers import trigger_next_pending_downloads

            trigger_next_pending_downloads(session)
        except Exception:
            logger.exception("Failed to trigger the next queued download after movie completion")


def _download_movie_media(
    session: Session,
    *,
    movie: Movie,
    download: MediaDownloadBase,
    row_progress: RowProgressWriter,
) -> tuple[DownloadResult, str]:
    tokens = DeviceAuthClient().get_token()
    client = MiddlewareClient(access_token=tokens.access_token if tokens else None)
    playback = client.get_movie_playback(movie.slug)
    if not playback.has_video or not playback.video_url:
        raise MediaUnavailableError(f"Daily Wire provides no playable video for '{movie.title}'")

    # Without sufficient membership Daily Wire may return the public trailer in
    # the movie endpoint. Never silently save that short fallback as the movie.
    if playback.trailer_url and playback.video_url == playback.trailer_url:
        raise MediaUnavailableError(
            f"The connected Daily Wire account does not provide access to the full movie '{movie.title}'"
        )
    if movie.duration and playback.duration and playback.duration < movie.duration * 0.5:
        raise MediaUnavailableError(
            f"Daily Wire returned only a preview for '{movie.title}', not the full movie"
        )

    info = probe(playback.video_url)
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
        source_url = playback.video_url
        format_downloaded = "video"
        use_hls = True
    else:
        source_url = playback.video_url
        format_downloaded = "video"
        use_hls = False

    remux = use_hls and get_settings().download_settings.remux_video_to_mp4
    extension = "mp4" if remux else info.suggested_extension
    destination = resolve_movie_output_path(
        download.local_media_profile.output_template,
        movie=movie,
        extension=extension,
    )
    download.file_path = str(destination)
    session.commit()

    if remux:
        result = _download_and_remux(source_url, str(destination), row_progress)
    elif use_hls:
        result = download_hls(source_url, str(destination), progress=row_progress)
    else:
        result = download_file(source_url, str(destination), progress=row_progress)
    return result, format_downloaded


def _download_and_remux(source_url: str, destination: str, progress: RowProgressWriter) -> DownloadResult:
    raw_path = destination + ".rawts"
    try:
        downloaded = download_hls(source_url, raw_path, progress=progress)
        remux_to_mp4(raw_path, destination, ffmpeg_path=get_settings().download_settings.ffmpeg_path)
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


def _truncate_message(message: str, limit: int = 20_000) -> str:
    return message if len(message) <= limit else "…" + message[-(limit - 1):]
