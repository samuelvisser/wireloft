from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.db.models import Episode, Show
from backend.db.models.media_download import MediaDownloadAttempt, MediaDownloadBase
from backend.types.download_profile_types import MediaDownloadStatus
from backend.types.local_media_profile_types import LocalMediaProfileType, PreferredFormat
from backend.utils.output_template import resolve_episode_output_path
from config import get_settings
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

from ._helpers import FORMAT_HEIGHTS, RowProgressWriter, refresh_episode_media_urls, select_rendition

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _AttemptResult:
    file_path: str
    bytes_downloaded: int
    format_downloaded: str


async def run_download_episode(s: Session, *, media_download_id: int, is_redownload: bool = False, progress=None) -> None:
    """Download one episode's media according to its media download row.

    The media URLs stored on the episode are used first; when they are missing or
    no longer usable, fresh ones are fetched from the Daily Wire API once. Only
    when those don't work either does the download fail.
    """
    download: Optional[MediaDownloadBase] = s.get(MediaDownloadBase, media_download_id)
    if download is None:
        raise ValueError(f"Media download {media_download_id} not found")

    episode: Optional[Episode] = s.get(Episode, download.media_item_id)
    if episode is None:
        raise ValueError(f"Episode {download.media_item_id} for download {media_download_id} not found")
    show: Show = episode.show
    profile = download.local_media_profile
    if profile.type != LocalMediaProfileType.SHOW.value:
        raise DownloadError("Episodes require a Show Local Media Profile")

    print(f"Starting download_episode for {episode.slug} ({profile.name})")

    download.download_status = MediaDownloadStatus.DOWNLOADING.value
    download.progress = 0
    download.error_message = None
    download.started_at = datetime.now(timezone.utc)
    download.finished_at = None
    # Recorded up front so it survives a failed attempt too, not just a
    # successful one: the download's log shows what kind of attempt this was
    # regardless of how it ends.
    download.is_redownload_attempt = is_redownload
    s.commit()

    want_audio = profile.preferred_format == PreferredFormat.FORMAT_AUDIO_ONLY.value
    row_progress = RowProgressWriter(media_download_id, task_progress=progress)

    try:
        try:
            result = _download_with_url_refresh(
                s,
                download=download,
                episode=episode,
                show=show,
                want_audio=want_audio,
                row_progress=row_progress,
            )
        except Exception as e:
            s.rollback()
            download.download_status = MediaDownloadStatus.ERROR.value
            download.error_message = _truncate_message(str(e))
            download.finished_at = datetime.now(timezone.utc)
            _record_attempt(s, download, is_redownload=is_redownload)
            s.commit()
            raise

        download.download_status = (
            MediaDownloadStatus.REDOWNLOADED.value if is_redownload else MediaDownloadStatus.DOWNLOADED.value
        )
        download.progress = 100
        download.downloaded_bytes = result.bytes_downloaded
        download.format_downloaded = result.format_downloaded
        download.file_path = result.file_path
        download.finished_at = datetime.now(timezone.utc)
        # Records what version was actually fetched, so a Download Profile can later
        # tell whether this file still needs replacing (e.g. still countdown-era)
        # instead of redownloading on every check.
        download.downloaded_publish_status = episode.publish_status
        if episode.downloaded_date is None:
            episode.downloaded_date = datetime.now(timezone.utc)
        if is_redownload:
            episode.redownloaded_date = datetime.now(timezone.utc)
        _record_attempt(s, download, is_redownload=is_redownload)
        s.commit()

        print(
            f"download_episode completed for {episode.slug}: "
            f"{result.format_downloaded} -> {result.file_path} ({result.bytes_downloaded} bytes)"
        )
    finally:
        # This download just freed a concurrency slot, one way or another;
        # immediately backfill it from the queue instead of leaving it idle
        # until the next full Download Profile sweep.
        _drain_next_pending_downloads(s)


def _record_attempt(s: Session, download: MediaDownloadBase, *, is_redownload: bool) -> None:
    """Append this attempt's outcome to the download's permanent ledger.

    download's own error_message/status/bytes get reset the moment the next
    attempt starts, so without this a previous error would simply vanish the
    instant someone clicks retry. Call this after the download row's own
    fields have been set to their final state for this attempt (status,
    error_message, finished_at, ...), right before committing.
    """
    s.add(MediaDownloadAttempt(
        media_download_id=download.id,
        is_redownload=is_redownload,
        status=download.download_status,
        error_message=download.error_message,
        downloaded_bytes=download.downloaded_bytes,
        format_downloaded=download.format_downloaded,
        started_at=download.started_at,
        finished_at=download.finished_at,
    ))


def _drain_next_pending_downloads(s: Session) -> None:
    try:
        from task_manager.tasks.workers.download_profile_worker._helpers import trigger_next_pending_downloads

        trigger_next_pending_downloads(s)
    except Exception:
        logger.exception("Failed to trigger the next pending download(s) after completion")


def _download_with_url_refresh(
        s: Session,
        *,
        download: MediaDownloadBase,
        episode: Episode,
        show: Show,
        want_audio: bool,
        row_progress: RowProgressWriter,
) -> _AttemptResult:
    """Try the stored media URL; on a missing/unusable URL refresh from DW once."""
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
            s, download=download, episode=episode, url=url, want_audio=want_audio, row_progress=row_progress
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
            s, download=download, episode=episode, url=url, want_audio=want_audio, row_progress=row_progress
        )


def _refresh(s: Session, *, episode: Episode, show: Show) -> None:
    try:
        refresh_episode_media_urls(s, episode=episode, show=show)
    except MediaUnavailableError:
        raise
    except Exception as e:
        raise MediaUnavailableError(
            f"Could not refresh media URLs from Daily Wire for '{episode.slug}': {e}"
        ) from e


def _attempt_download(
        s: Session,
        *,
        download: MediaDownloadBase,
        episode: Episode,
        url: str,
        want_audio: bool,
        row_progress: RowProgressWriter,
) -> _AttemptResult:
    """Probe the URL, pick what to fetch, and download it to its final path."""
    profile = download.local_media_profile
    info = probe(url)

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

    dest = resolve_episode_output_path(
        profile.output_template,
        episode=episode,
        extension=extension,
    )
    download.file_path = str(dest)
    s.commit()

    if remux_video:
        result = _download_and_remux_to_mp4(source_url, str(dest), row_progress=row_progress)
    elif use_hls:
        result = download_hls(source_url, str(dest), progress=row_progress)
    else:
        result = download_file(source_url, str(dest), progress=row_progress)

    return _AttemptResult(
        file_path=result.path,
        bytes_downloaded=result.bytes_downloaded,
        format_downloaded=format_downloaded,
    )


def _download_and_remux_to_mp4(source_url: str, dest_path: str, *, row_progress: RowProgressWriter) -> DownloadResult:
    """Download an HLS video to a temporary .ts file, then remux it into dest_path.

    The raw TS download reports progress as usual; the remux itself is a fast
    stream copy (no re-encoding) so it isn't broken out into its own progress
    phase. The temporary file is always cleaned up, even on failure.
    """
    raw_ts_path = dest_path + ".rawts"
    try:
        ts_result = download_hls(source_url, raw_ts_path, progress=row_progress)
        remux_to_mp4(raw_ts_path, dest_path, ffmpeg_path=get_settings().download_settings.ffmpeg_path)
    finally:
        _remove_quietly(raw_ts_path)

    return DownloadResult(
        path=dest_path,
        bytes_downloaded=ts_result.bytes_downloaded,
        segments_downloaded=ts_result.segments_downloaded,
    )


def _truncate_message(message: str, limit: int = 20_000) -> str:
    """Cap a stored error message, keeping its *end* rather than its start.

    This is the full text shown in a download's log, so the cap is generous -
    it exists only to bound a pathological case, not to compact the message
    for a table row (the UI truncates that display on its own). Errors built
    from a diagnostic tail (e.g. ffmpeg's own last output lines) put the
    actually useful part at the end; a plain head slice (``msg[:limit]``)
    would just as easily cut that off and keep only a generic prefix instead.
    """
    if len(message) <= limit:
        return message
    return "…" + message[-(limit - 1):]


def _remove_quietly(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
