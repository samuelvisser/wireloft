from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.db.models import Episode, Show
from backend.db.models.media_download import MediaDownloadBase
from backend.types.download_profile_types import MediaDownloadStatus
from backend.types.local_media_profile_types import PreferredFormat
from backend.utils.output_template import resolve_episode_output_path
from dailywire_downloader import (
    DownloadError,
    MediaKind,
    MediaUnavailableError,
    download_file,
    download_hls,
    probe,
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

    print(f"Starting download_episode for {episode.slug} ({profile.name})")

    download.download_status = MediaDownloadStatus.DOWNLOADING.value
    download.progress = 0
    download.error_message = None
    download.started_at = datetime.now(timezone.utc)
    download.finished_at = None
    s.commit()

    want_audio = profile.preferred_format == PreferredFormat.FORMAT_AUDIO_ONLY.value
    row_progress = RowProgressWriter(media_download_id, task_progress=progress)

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
        download.error_message = str(e)[:1000]
        download.finished_at = datetime.now(timezone.utc)
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
    if episode.downloaded_date is None:
        episode.downloaded_date = datetime.now(timezone.utc)
    if is_redownload:
        episode.redownloaded_date = datetime.now(timezone.utc)
    s.commit()

    print(
        f"download_episode completed for {episode.slug}: "
        f"{result.format_downloaded} -> {result.file_path} ({result.bytes_downloaded} bytes)"
    )


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

    dest = resolve_episode_output_path(
        profile.output_template,
        episode=episode,
        extension=info.suggested_extension,
    )
    download.file_path = str(dest)
    s.commit()

    if use_hls:
        result = download_hls(source_url, str(dest), progress=row_progress)
    else:
        result = download_file(source_url, str(dest), progress=row_progress)

    return _AttemptResult(
        file_path=result.path,
        bytes_downloaded=result.bytes_downloaded,
        format_downloaded=format_downloaded,
    )
