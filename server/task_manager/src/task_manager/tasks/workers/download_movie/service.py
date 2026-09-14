from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.db.models import Movie, MovieExtra
from backend.db.models.media_download import MediaDownloadBase
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from backend.types.local_media_profile_types import LocalMediaProfileType, PreferredFormat
from backend.types.media_types import MediaType
from backend.utils.artifact_identity import inspect_artifact
from task_manager.tasks.helpers.downloads.download_files import remove_download_artifacts
from task_manager.tasks.helpers.downloads.download_modes import effective_download_mode
from task_manager.tasks.helpers.downloads.download_paths import (
    TemporaryDownloadWorkspace,
    create_temporary_download_workspace,
    publish_temporary_download,
    reserve_unique_download_path,
)
from backend.utils.output_template import resolve_movie_output_path
from config import get_settings
from config.settings.submodels import DownloadMode
from dailywire_api.dw_api.movie import MovieMiddlewareClient
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
    owned_paths: list[str] = []
    temporary_workspaces: list[TemporaryDownloadWorkspace] = []

    try:
        _ensure_not_cancelled(progress)
        result, format_downloaded = _download_movie_media(
            session,
            movie=movie,
            media=media,
            download=download,
            task_progress=task_progress,
            cancellation=progress,
            owned_paths=owned_paths,
            temporary_workspaces=temporary_workspaces,
        )
        _ensure_not_cancelled(progress)

        session.rollback()
        session.expire_all()
        download = session.get(MediaDownloadBase, media_download_id)
        if download is None:
            remove_download_artifacts(result.path)
            raise DownloadCancelled("Media download was deleted while the worker was running")
        _ensure_not_cancelled(progress)

        artifact_identity = inspect_artifact(result.path)
        download.file_path = result.path
        download.artifact_stat_dev = artifact_identity.stat_dev
        download.artifact_stat_ino = artifact_identity.stat_ino
        download.artifact_size_bytes = artifact_identity.size_bytes
        download.artifact_fingerprint = artifact_identity.fingerprint
        download.artifact_status = MediaDownloadArtifactStatus.AVAILABLE.value
        download.artifact_error = None
        download.automatic_retry_suppressed = False
        download.downloaded_bytes = result.bytes_downloaded
        download.format_downloaded = format_downloaded
        download.downloaded_at = datetime.now(timezone.utc)

        media = session.get(MovieExtra if download.type == MediaType.MOVIE_EXTRA.value else Movie, download.media_item_id)

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
    except DownloadCancelled:
        session.rollback()
        for path in owned_paths:
            remove_download_artifacts(path)
        raise
    except Exception:
        session.rollback()
        for path in owned_paths:
            remove_download_artifacts(path)
        raise
    finally:
        for workspace in temporary_workspaces:
            workspace.cleanup()


def _download_movie_media(
    session: Session,
    *,
    movie: Movie,
    media: Movie | MovieExtra,
    download: MediaDownloadBase,
    task_progress: TaskProgressWriter,
    cancellation,
    owned_paths: list[str],
    temporary_workspaces: list[TemporaryDownloadWorkspace],
) -> tuple[DownloadResult, str]:
    _ensure_not_cancelled(cancellation)

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
    settings = get_settings().download_settings

    # Authentication, playback lookup and probing may all block on the internet.
    # Snapshot the required local values and release the transaction first.
    session.rollback()
    tokens = DeviceAuthClient().get_token()
    client = MovieMiddlewareClient(access_token=tokens.access_token if tokens else None)
    if is_extra:
        source_playback_url = _movie_extra_playback_url(
            client,
            movie_slug=movie_slug,
            official_trailer_id=official_trailer_id,
            extra_id=media_id,
            extra_slug=extra_slug,
            extra_title=extra_title,
        )
        _ensure_not_cancelled(cancellation)
    else:
        playback = client.get_movie_playback(movie_slug)
        _ensure_not_cancelled(cancellation)
        if not playback.has_video or not playback.video_url:
            raise MediaUnavailableError(f"Daily Wire provides no playable video for '{movie_title}'")
        source_playback_url = playback.video_url
        if playback.trailer_url and source_playback_url == playback.trailer_url:
            raise MediaUnavailableError(
                f"The connected Daily Wire account does not provide access to the full movie '{movie_title}'"
            )
        if movie_duration and playback.duration and playback.duration < movie_duration * 0.5:
            raise MediaUnavailableError(
                f"Daily Wire returned only a preview for '{movie_title}', not the full movie"
            )

    info = probe(source_playback_url)
    _ensure_not_cancelled(cancellation)
    if info.kind is MediaKind.HLS_MASTER:
        requested_height = FORMAT_HEIGHTS.get(preferred_format)
        if requested_height is None:
            raise DownloadError(f"Unsupported preferred format '{preferred_format}'")
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

    task_progress.set_selected_format(format_downloaded)

    remux = use_hls and settings.remux_video_to_mp4
    extension = "mp4" if remux else info.suggested_extension

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
        extension=extension,
    )

    # Resolving the destination needs ORM-backed movie metadata. Release that
    # transaction again before the potentially long media transfer.
    session.rollback()

    if download_mode is DownloadMode.TEMPORARY:
        workspace = create_temporary_download_workspace(
            settings.temporary_download_root,
            requested_destination,
        )
        keep_workspace = False
        published_destination: str | None = None
        try:
            result = _perform_download(
                source_url,
                str(workspace.path),
                remux=remux,
                use_hls=use_hls,
                task_progress=task_progress,
                cancellation=cancellation,
            )
            _ensure_not_cancelled(cancellation)
            destination = publish_temporary_download(
                workspace.path,
                requested_destination,
            )
            published_destination = str(destination)
            owned_paths.append(published_destination)
            temporary_workspaces.append(workspace)
            keep_workspace = True
            result = DownloadResult(
                path=published_destination,
                bytes_downloaded=result.bytes_downloaded,
                segments_downloaded=result.segments_downloaded,
            )
        except BaseException:
            if published_destination is not None:
                remove_download_artifacts(published_destination)
            raise
        finally:
            if not keep_workspace:
                workspace.cleanup()
    else:
        reservation = reserve_unique_download_path(requested_destination)
        destination = reservation.path
        owned_paths.append(str(destination))
        try:
            download.file_path = str(destination)
            session.commit()
            result = _perform_download(
                source_url,
                str(destination),
                remux=remux,
                use_hls=use_hls,
                task_progress=task_progress,
                cancellation=cancellation,
            )
        finally:
            reservation.release_if_unclaimed()

    return result, format_downloaded


def _perform_download(
        source_url: str,
        destination: str,
        *,
        remux: bool,
        use_hls: bool,
        task_progress: TaskProgressWriter,
        cancellation,
) -> DownloadResult:
    if remux:
        return _download_and_remux(
            source_url,
            destination,
            task_progress,
            cancellation,
        )
    if use_hls:
        return download_hls(
            source_url,
            destination,
            progress=task_progress,
            should_cancel=cancellation,
        )
    return download_file(
        source_url,
        destination,
        progress=task_progress,
        should_cancel=cancellation,
    )


def _movie_extra_playback_url(
    client: MovieMiddlewareClient,
    *,
    movie_slug: str,
    official_trailer_id: int | None,
    extra_id: int,
    extra_slug: str | None,
    extra_title: str | None,
) -> str:
    if not extra_slug:
        raise MediaUnavailableError(f"Movie extra {extra_id} has no Daily Wire slug")

    try:
        playback = client.get_movie_extra_playback(extra_slug)
        source_url = playback.video_url
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


def _truncate_message(message: str, limit: int = 20_000) -> str:
    return message if len(message) <= limit else "…" + message[-(limit - 1):]
