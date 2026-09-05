from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.db.models import Movie, MovieExtra
from backend.db.models.media_download import MediaDownloadAttempt, MediaDownloadBase
from backend.types.download_profile_types import MediaDownloadArtifactStatus
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
from task_manager.scheduler.results import TaskResult
from task_manager.tasks.workers.download_episode._helpers import (
    FORMAT_HEIGHTS,
    TaskProgressWriter,
    select_rendition,
)


def _ensure_not_cancelled(progress) -> None:
    if progress is not None and callable(progress) and progress():
        raise DownloadCancelled("Download was canceled")


async def run_download_movie(
        session: Session,
        *,
        media_download_id: int,
        is_redownload: bool = False,
        progress=None,
) -> TaskResult:
    """Produce one movie/movie-extra artifact; TaskRun owns execution state."""
    started_at = datetime.now(timezone.utc)
    download: Optional[MediaDownloadBase] = session.get(MediaDownloadBase, media_download_id)
    if download is None:
        raise DownloadCancelled(f"Media download {media_download_id} was deleted before it started")

    if download.type == MediaType.MOVIE_EXTRA.value:
        media = session.get(MovieExtra, download.media_item_id)
        if media is None:
            raise ValueError(f"Movie extra {download.media_item_id} for download {media_download_id} not found")
        movie = media.movie
    else:
        media = session.get(Movie, download.media_item_id)
        if media is None:
            raise ValueError(f"Movie {download.media_item_id} for download {media_download_id} not found")
        movie = media

    profile = download.local_media_profile
    if profile.type != LocalMediaProfileType.MOVIE.value:
        raise DownloadError("Movies and movie extras require a Movie Local Media Profile")
    if profile.preferred_format == PreferredFormat.FORMAT_AUDIO_ONLY.value:
        raise DownloadError("Movies and movie extras require a video Local Media Profile")

    if progress is not None:
        progress.set(0, f"Starting download for {media.title}")
    task_progress = TaskProgressWriter(progress)

    try:
        _ensure_not_cancelled(progress)
        result, format_downloaded = _download_movie_media(
            session,
            movie=movie,
            media=media,
            download=download,
            task_progress=task_progress,
            cancellation=progress,
        )
        _ensure_not_cancelled(progress)

        session.rollback()
        session.expire_all()
        download = session.get(MediaDownloadBase, media_download_id)
        if download is None:
            remove_download_artifacts(result.path)
            raise DownloadCancelled("Media download was deleted while the worker was running")
        _ensure_not_cancelled(progress)

        download.file_path = result.path
        download.artifact_status = MediaDownloadArtifactStatus.AVAILABLE.value
        download.artifact_error = None
        download.automatic_retry_suppressed = False
        download.downloaded_bytes = result.bytes_downloaded
        download.format_downloaded = format_downloaded
        download.downloaded_at = datetime.now(timezone.utc)

        media = session.get(MovieExtra if download.type == MediaType.MOVIE_EXTRA.value else Movie, download.media_item_id)
        if media is not None:
            media.downloaded_date = media.downloaded_date or download.downloaded_at

        _record_attempt(
            session,
            download,
            is_redownload=is_redownload,
            status="redownloaded" if is_redownload else "downloaded",
            error_message=None,
            downloaded_bytes=result.bytes_downloaded,
            format_downloaded=format_downloaded,
            started_at=started_at,
            finished_at=download.downloaded_at,
        )
        session.commit()

        return TaskResult(
            summary=f"Downloaded {getattr(media, 'title', movie.title)}",
            data={
                "media_download_id": media_download_id,
                "downloaded_bytes": result.bytes_downloaded,
                "format_downloaded": format_downloaded,
                "file_path": result.path,
                "is_redownload": is_redownload,
            },
        )
    except DownloadCancelled as exc:
        session.rollback()
        remove_download_artifacts(getattr(download, "file_path", None))
        _record_terminal_attempt_if_present(
            session,
            media_download_id=media_download_id,
            is_redownload=is_redownload,
            status="cancelled",
            error_message=_truncate_message(str(exc)),
            started_at=started_at,
        )
        raise
    except Exception as exc:
        session.rollback()
        remove_download_artifacts(getattr(download, "file_path", None))
        _record_terminal_attempt_if_present(
            session,
            media_download_id=media_download_id,
            is_redownload=is_redownload,
            status="error",
            error_message=_truncate_message(str(exc)),
            started_at=started_at,
        )
        raise


def _download_movie_media(
    session: Session,
    *,
    movie: Movie,
    media: Movie | MovieExtra,
    download: MediaDownloadBase,
    task_progress: TaskProgressWriter,
    cancellation,
) -> tuple[DownloadResult, str]:
    _ensure_not_cancelled(cancellation)
    tokens = DeviceAuthClient().get_token()
    client = MiddlewareClient(access_token=tokens.access_token if tokens else None)
    if isinstance(media, MovieExtra):
        source_playback_url = _movie_extra_playback_url(client, movie=movie, extra=media)
        _ensure_not_cancelled(cancellation)
    else:
        playback = client.get_movie_playback(movie.slug)
        _ensure_not_cancelled(cancellation)
        if not playback.has_video or not playback.video_url:
            raise MediaUnavailableError(f"Daily Wire provides no playable video for '{movie.title}'")
        source_playback_url = playback.video_url
        if playback.trailer_url and source_playback_url == playback.trailer_url:
            raise MediaUnavailableError(
                f"The connected Daily Wire account does not provide access to the full movie '{movie.title}'"
            )
        if movie.duration and playback.duration and playback.duration < movie.duration * 0.5:
            raise MediaUnavailableError(
                f"Daily Wire returned only a preview for '{movie.title}', not the full movie"
            )

    info = probe(source_playback_url)
    _ensure_not_cancelled(cancellation)
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
        extension=extension,
    )
    download.file_path = str(destination)
    session.commit()

    if remux:
        result = _download_and_remux(
            source_url,
            str(destination),
            task_progress,
            cancellation,
        )
    elif use_hls:
        result = download_hls(
            source_url,
            str(destination),
            progress=task_progress,
            should_cancel=cancellation,
        )
    else:
        result = download_file(
            source_url,
            str(destination),
            progress=task_progress,
            should_cancel=cancellation,
        )
    return result, format_downloaded


def _movie_extra_playback_url(
    client: MiddlewareClient,
    *,
    movie: Movie,
    extra: MovieExtra,
) -> str:
    try:
        playback = client.get_movie_extra_playback(extra.slug)
        source_url = playback.video_url
    except Exception:
        if movie.official_trailer_id != extra.id:
            raise
        source_url = None

    if not source_url and movie.official_trailer_id == extra.id:
        source_url = client.get_movie_playback(movie.slug).trailer_url
    if not source_url:
        raise MediaUnavailableError(
            f"Daily Wire provides no playable video for movie extra '{extra.title}'"
        )
    return source_url


def _download_and_remux(
        source_url: str,
        destination: str,
        progress: TaskProgressWriter,
        cancellation,
) -> DownloadResult:
    raw_path = destination + ".rawts"
    try:
        downloaded = download_hls(
            source_url,
            raw_path,
            progress=progress,
            should_cancel=cancellation,
        )
        _ensure_not_cancelled(cancellation)
        remux_to_mp4(
            raw_path,
            destination,
            ffmpeg_path=get_settings().download_settings.ffmpeg_path,
            should_cancel=cancellation,
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


def _record_attempt(
        session: Session,
        download: MediaDownloadBase,
        *,
        is_redownload: bool,
        status: str,
        error_message: Optional[str],
        downloaded_bytes: Optional[int],
        format_downloaded: Optional[str],
        started_at: datetime,
        finished_at: datetime,
) -> None:
    session.add(MediaDownloadAttempt(
        media_download_id=download.id,
        is_redownload=is_redownload,
        status=status,
        error_message=error_message,
        downloaded_bytes=downloaded_bytes,
        format_downloaded=format_downloaded,
        started_at=started_at,
        finished_at=finished_at,
    ))


def _record_terminal_attempt_if_present(
        session: Session,
        *,
        media_download_id: int,
        is_redownload: bool,
        status: str,
        error_message: str,
        started_at: datetime,
) -> None:
    current = session.get(MediaDownloadBase, media_download_id)
    if current is None:
        return
    _record_attempt(
        session,
        current,
        is_redownload=is_redownload,
        status=status,
        error_message=error_message,
        downloaded_bytes=None,
        format_downloaded=None,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
    )
    session.commit()


def _truncate_message(message: str, limit: int = 20_000) -> str:
    return message if len(message) <= limit else "…" + message[-(limit - 1):]
