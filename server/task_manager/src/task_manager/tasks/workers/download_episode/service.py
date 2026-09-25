from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.db.models import Episode, Show
from backend.db.models.media_download import MediaDownloadBase
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from backend.types.local_media_profile_types import LocalMediaProfileType, PreferredFormat
from backend.utils.artifact_identity import inspect_artifact
from backend.utils.output_template import resolve_episode_output_path
from config import get_settings
from config.network import is_no_internet_error
from dailywire_downloader import DownloadCancelled, DownloadError, MediaUnavailableError
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

from ._helpers import refresh_episode_media_urls

logger = logging.getLogger(__name__)


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
    execution: DownloadExecution | None = None

    try:
        ensure_not_cancelled(progress)
        execution = _download_with_url_refresh(
            s,
            download=download,
            episode=episode,
            show=show,
            want_audio=want_audio,
            task_progress=task_progress,
            cancellation=progress,
        )
        ensure_not_cancelled(progress)

        # Re-read before publishing durable artifact state so a stale worker can
        # never resurrect a MediaDownload that was deleted during the transfer.
        s.rollback()
        s.expire_all()
        download = s.get(MediaDownloadBase, media_download_id)
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
        download.downloaded_at = datetime.now(timezone.utc)

        episode = s.get(Episode, download.media_item_id)
        if episode is not None and hasattr(download, "downloaded_publish_status"):
            download.downloaded_publish_status = episode.publish_status

        s.commit()

        # The executor owns the final 100% transition. Avoid a second progress
        # checkpoint after the artifact commit so late cancellation cannot turn a
        # successfully published artifact into a canceled TaskRun.
        print(
            f"download_episode completed for {getattr(episode, 'slug', media_download_id)}: "
            f"{execution.format_downloaded} -> {execution.result.path} "
            f"({execution.result.bytes_downloaded} bytes)"
        )
        return TaskResult(
            summary=f"Downloaded {getattr(episode, 'title', 'episode')}",
            data={
                "media_download_id": media_download_id,
                "downloaded_bytes": execution.result.bytes_downloaded,
                "format_downloaded": execution.format_downloaded,
                "file_path": execution.result.path,
                "thumbnail_path": execution.thumbnail_path,
                "is_redownload": is_redownload,
            },
        )
    except DownloadCancelled:
        s.rollback()
        if execution is not None:
            remove_download_artifacts(execution.result.path, execution.thumbnail_path)
        raise
    except Exception:
        s.rollback()
        if execution is not None:
            remove_download_artifacts(execution.result.path, execution.thumbnail_path)
        raise
    finally:
        # Temporary-mode publication keeps its recovery record until the database
        # transaction above commits. Normal completion removes that workspace here;
        # an unclean shutdown leaves it for startup reconciliation.
        if execution is not None:
            execution.cleanup_workspace()


def _download_with_url_refresh(
    s: Session,
    *,
    download: MediaDownloadBase,
    episode: Episode,
    show: Show,
    want_audio: bool,
    task_progress: TaskProgressWriter,
    cancellation,
) -> DownloadExecution:
    """Try the stored media URL; on a missing/unusable URL refresh from DW once."""
    ensure_not_cancelled(cancellation)
    url = episode.audio_url if want_audio else episode.video_url
    refreshed = False

    if not url:
        _refresh(s, episode=episode, show=show)
        refreshed = True
        url = episode.audio_url if want_audio else episode.video_url
        if not url:
            kind = "audio" if want_audio else "video"
            raise MediaUnavailableError(
                f"Daily Wire provides no {kind} URL for episode '{episode.slug}'"
            )

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
    except MediaUnavailableError as exc:
        if is_no_internet_error(exc):
            raise
        if refreshed:
            raise
        logger.info(
            "Stored media URL for %s unusable; refreshing from Daily Wire",
            episode.slug,
        )
        _refresh(s, episode=episode, show=show)
        url = episode.audio_url if want_audio else episode.video_url
        if not url:
            kind = "audio" if want_audio else "video"
            raise MediaUnavailableError(
                f"Daily Wire provides no {kind} URL for episode '{episode.slug}'"
            )
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
) -> DownloadExecution:
    """Resolve an episode source and hand its transfer/publication to the shared engine."""
    profile = download.local_media_profile
    preferred_format = profile.preferred_format
    output_template = profile.output_template
    download_mode = effective_download_mode(profile)
    thumbnail_mode = effective_thumbnail_mode(profile)
    thumbnail_url = select_thumbnail_url(episode)
    settings = get_settings().download_settings

    # Probe may block on DNS/HTTP. Everything it needs is now a plain value, so
    # release the ORM transaction before touching the network.
    s.rollback()
    source = resolve_download_source(
        url,
        preferred_format=preferred_format,
        audio_only=want_audio,
        remux_video_to_mp4=settings.remux_video_to_mp4,
        cancellation=cancellation,
    )
    task_progress.set_selected_format(source.format_downloaded)

    requested_destination = resolve_episode_output_path(
        output_template,
        episode=episode,
        local_media_profile=profile,
        media_download=download,
        extension=source.extension,
    )

    # Rendering can lazily refresh the episode after the probe rollback. Release
    # that transaction too before the potentially long media transfer.
    s.rollback()

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
        s.commit()

    return execute_download_plan(
        plan,
        task_progress=task_progress,
        cancellation=cancellation,
        on_direct_destination_reserved=persist_direct_destination,
    )
