from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.db.models import Episode, Show
from backend.db.models.media_download import MediaDownloadBase
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from backend.types.local_media_profile_types import LocalMediaProfileType, PreferredFormat
from backend.utils.download_files import remove_download_artifacts
from backend.utils.output_template import resolve_episode_output_path
from config import get_settings
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

from ._helpers import FORMAT_HEIGHTS, TaskProgressWriter, refresh_episode_media_urls, select_rendition

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _AttemptResult:
    file_path: str
    bytes_downloaded: int
    format_downloaded: str


def _ensure_not_cancelled(progress) -> None:
    if progress is not None and callable(progress) and progress():
        raise DownloadCancelled("Download was canceled")


async def run_download_episode(
        s: Session,
        *,
        media_download_id: int,
        is_redownload: bool = False,
        progress=None,
) -> TaskResult:
    """Produce one episode artifact while TaskRun owns all changing execution state."""
    download: Optional[MediaDownloadBase] = s.get(MediaDownloadBase, media_download_id)
    if download is None:
        raise DownloadCancelled(f"Media download {media_download_id} was deleted before it started")

    episode: Optional[Episode] = s.get(Episode, download.media_item_id)
    if episode is None:
        raise ValueError(f"Episode {download.media_item_id} for download {media_download_id} not found")
    show: Show = episode.show
    profile = download.local_media_profile
    if profile.type != LocalMediaProfileType.SHOW.value:
        raise DownloadError("Episodes require a Show Local Media Profile")

    print(f"Starting download_episode for {episode.slug} ({profile.name})")
    if progress is not None:
        progress.set(0, f"Starting download for {episode.title}")

    want_audio = profile.preferred_format == PreferredFormat.FORMAT_AUDIO_ONLY.value
    task_progress = TaskProgressWriter(progress)

    try:
        _ensure_not_cancelled(progress)
        result = _download_with_url_refresh(
            s,
            download=download,
            episode=episode,
            show=show,
            want_audio=want_audio,
            task_progress=task_progress,
            cancellation=progress,
        )
        _ensure_not_cancelled(progress)

        # The worker may have been canceled/deleted while the downloader was
        # finishing. Re-read before publishing the persistent artifact so a stale
        # worker can never resurrect domain state after generic task cancellation.
        s.rollback()
        s.expire_all()
        download = s.get(MediaDownloadBase, media_download_id)
        if download is None:
            remove_download_artifacts(result.file_path)
            raise DownloadCancelled("Media download was deleted while the worker was running")
        _ensure_not_cancelled(progress)

        download.file_path = result.file_path
        download.artifact_status = MediaDownloadArtifactStatus.AVAILABLE.value
        download.artifact_error = None
        download.automatic_retry_suppressed = False
        download.downloaded_bytes = result.bytes_downloaded
        download.format_downloaded = result.format_downloaded
        download.downloaded_at = datetime.now(timezone.utc)

        episode = s.get(Episode, download.media_item_id)
        if episode is not None:
            if hasattr(download, "downloaded_publish_status"):
                download.downloaded_publish_status = episode.publish_status
            if episode.downloaded_date is None:
                episode.downloaded_date = download.downloaded_at
            if is_redownload:
                episode.redownloaded_date = download.downloaded_at

        s.commit()

        # The executor owns the final 100% transition. Avoid a second progress
        # checkpoint after the artifact commit: cancellation discovered at that
        # point must not turn a successfully published artifact into a canceled
        # TaskRun.
        print(
            f"download_episode completed for {getattr(episode, 'slug', media_download_id)}: "
            f"{result.format_downloaded} -> {result.file_path} ({result.bytes_downloaded} bytes)"
        )
        return TaskResult(
            summary=f"Downloaded {getattr(episode, 'title', 'episode')}",
            data={
                "media_download_id": media_download_id,
                "downloaded_bytes": result.bytes_downloaded,
                "format_downloaded": result.format_downloaded,
                "file_path": result.file_path,
                "is_redownload": is_redownload,
            },
        )
    except DownloadCancelled:
        s.rollback()
        remove_download_artifacts(getattr(download, "file_path", None))
        raise
    except Exception:
        s.rollback()
        remove_download_artifacts(getattr(download, "file_path", None))
        raise


def _download_with_url_refresh(
        s: Session,
        *,
        download: MediaDownloadBase,
        episode: Episode,
        show: Show,
        want_audio: bool,
        task_progress: TaskProgressWriter,
        cancellation,
) -> _AttemptResult:
    """Try the stored media URL; on a missing/unusable URL refresh from DW once."""
    _ensure_not_cancelled(cancellation)
    url = episode.audio_url if want_audio else episode.video_url
    refreshed = False

    if not url:
        _refresh(s, episode=episode, show=show)
        refreshed = True
        url = episode.audio_url if want_audio else episode.video_url
        if not url:
            kind = "audio" if want_audio else "video"
            raise MediaUnavailableError(f"Daily Wire provides no {kind} URL for episode '{episode.slug}'")

    try:
        return _attempt_download(
            s,
            download=download,
            episode=episode,
            url=url,
            want_audio=want_audio,
            task_progress=task_progress,
            cancellation=cancellation,
        )
    except MediaUnavailableError:
        if refreshed:
            raise
        logger.info("Stored media URL for %s unusable; refreshing from Daily Wire", episode.slug)
        _refresh(s, episode=episode, show=show)
        url = episode.audio_url if want_audio else episode.video_url
        if not url:
            kind = "audio" if want_audio else "video"
            raise MediaUnavailableError(f"Daily Wire provides no {kind} URL for episode '{episode.slug}'")
        return _attempt_download(
            s,
            download=download,
            episode=episode,
            url=url,
            want_audio=want_audio,
            task_progress=task_progress,
            cancellation=cancellation,
        )


def _refresh(s: Session, *, episode: Episode, show: Show) -> None:
    try:
        refresh_episode_media_urls(s, episode=episode, show=show)
    except MediaUnavailableError:
        raise
    except Exception as exc:
        raise MediaUnavailableError(
            f"Could not refresh media URLs from Daily Wire for '{episode.slug}': {exc}"
        ) from exc


def _attempt_download(
        s: Session,
        *,
        download: MediaDownloadBase,
        episode: Episode,
        url: str,
        want_audio: bool,
        task_progress: TaskProgressWriter,
        cancellation,
) -> _AttemptResult:
    """Probe the URL, pick what to fetch, and download it to its final path."""
    profile = download.local_media_profile
    _ensure_not_cancelled(cancellation)
    info = probe(url)
    _ensure_not_cancelled(cancellation)

    if want_audio:
        if info.kind is MediaKind.HLS_MASTER:
            raise DownloadError("Audio URL unexpectedly returned an HLS master playlist")
        source_url = url
        format_downloaded = "audio"
        use_hls = info.kind is MediaKind.HLS_MEDIA
    else:
        if info.kind is MediaKind.HLS_MASTER:
            requested_height = FORMAT_HEIGHTS.get(profile.preferred_format)
            if requested_height is None:
                raise DownloadError(f"Unsupported preferred format '{profile.preferred_format}'")
            rendition = select_rendition(info.renditions, requested_height)
            source_url = rendition.url
            format_downloaded = rendition.resolution or "video"
            use_hls = True
        elif info.kind is MediaKind.HLS_MEDIA:
            source_url = url
            format_downloaded = "video"
            use_hls = True
        else:
            source_url = url
            format_downloaded = "video"
            use_hls = False

    remux_video = not want_audio and use_hls and get_settings().download_settings.remux_video_to_mp4
    extension = "mp4" if remux_video else info.suggested_extension
    destination = resolve_episode_output_path(
        profile.output_template,
        episode=episode,
        extension=extension,
    )

    # The expected artifact location is domain data, not execution state.
    download.file_path = str(destination)
    s.commit()

    if remux_video:
        result = _download_and_remux_to_mp4(
            source_url,
            str(destination),
            task_progress=task_progress,
            cancellation=cancellation,
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

    return _AttemptResult(
        file_path=result.path,
        bytes_downloaded=result.bytes_downloaded,
        format_downloaded=format_downloaded,
    )


def _download_and_remux_to_mp4(
        source_url: str,
        dest_path: str,
        *,
        task_progress: TaskProgressWriter,
        cancellation,
) -> DownloadResult:
    raw_ts_path = dest_path + ".rawts"
    try:
        ts_result = download_hls(
            source_url,
            raw_ts_path,
            progress=task_progress,
            should_cancel=cancellation,
        )
        _ensure_not_cancelled(cancellation)
        remux_to_mp4(
            raw_ts_path,
            dest_path,
            ffmpeg_path=get_settings().download_settings.ffmpeg_path,
            should_cancel=cancellation,
        )
    finally:
        _remove_quietly(raw_ts_path)

    return DownloadResult(
        path=dest_path,
        bytes_downloaded=ts_result.bytes_downloaded,
        segments_downloaded=ts_result.segments_downloaded,
    )


def _truncate_message(message: str, limit: int = 20_000) -> str:
    if len(message) <= limit:
        return message
    return "…" + message[-(limit - 1):]


def _remove_quietly(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass