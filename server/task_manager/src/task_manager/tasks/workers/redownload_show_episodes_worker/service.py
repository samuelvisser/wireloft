from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import DownloadProfileBase, Episode, Show
from backend.db.models.media_download import EpisodeMediaDownload
from backend.types.download_profile_types import MediaDownloadStatus
from backend.types.media_types import MediaType
from backend.utils.download_files import remove_download_artifacts
from backend.utils.output_template import resolve_episode_output_path
from task_manager.scheduler.db import TaskDefinition, TaskRun
from task_manager.scheduler.types import TaskStatus
from task_manager.tasks.helpers.progress import update_progress
from task_manager.tasks.workers.download_attempt import serialize_download_attempt
from task_manager.tasks.workers.download_profile_worker._helpers import (
    get_download_profile_episodes,
    trigger_next_pending_downloads,
)

_POLL_INTERVAL_SECONDS = 0.5
_COMPLETED_STATUSES = {
    MediaDownloadStatus.DOWNLOADED.value,
    MediaDownloadStatus.REDOWNLOADED.value,
}


@dataclass(frozen=True)
class RedownloadTarget:
    media_download_id: int
    attempt_generation: int
    episode_title: str


def _selected_profiles(
        s: Session,
        *,
        show_id: int,
        download_profile_id: int | None,
) -> list[DownloadProfileBase]:
    stmt = select(DownloadProfileBase).where(DownloadProfileBase.show_id == show_id)
    if download_profile_id is not None:
        stmt = stmt.where(DownloadProfileBase.id == download_profile_id)
    profiles = list(s.scalars(stmt.order_by(DownloadProfileBase.id.asc())))
    if download_profile_id is not None and not profiles:
        raise ValueError("Download Profile is not attached to this show")
    return profiles


def _target_episode_profiles(
        s: Session,
        profiles: list[DownloadProfileBase],
) -> list[tuple[Episode, DownloadProfileBase]]:
    """Union profile scopes while deduplicating rows that share a Local Media Profile."""
    targets: dict[tuple[int, int], tuple[Episode, DownloadProfileBase]] = {}
    for profile in profiles:
        for episode in get_download_profile_episodes(s, profile):
            targets[(episode.id, profile.local_media_profile_id)] = (episode, profile)
    return list(targets.values())


def _reset_existing_download(
        s: Session,
        download: EpisodeMediaDownload,
        *,
        episode: Episode,
        profile: DownloadProfileBase,
) -> RedownloadTarget:
    """Cancel the old generation, remove its artifacts, and arm a fresh download."""
    old_path = download.file_path
    new_path = str(resolve_episode_output_path(profile.local_media_profile.output_template, episode=episode))

    download.attempt_generation += 1
    download.download_profile_id = profile.id
    download.download_status = MediaDownloadStatus.PENDING.value
    download.progress = 0
    download.error_message = None
    download.downloaded_bytes = None
    download.format_downloaded = None
    download.started_at = None
    download.finished_at = None
    download.downloaded_publish_status = None
    download.is_redownload_attempt = True
    download.file_path = new_path
    s.flush()

    remove_download_artifacts(old_path)
    if Path(new_path) != Path(old_path):
        remove_download_artifacts(new_path)

    return RedownloadTarget(
        media_download_id=download.id,
        attempt_generation=download.attempt_generation,
        episode_title=episode.title,
    )


def _create_download(
        s: Session,
        *,
        episode: Episode,
        profile: DownloadProfileBase,
) -> RedownloadTarget:
    path = str(resolve_episode_output_path(profile.local_media_profile.output_template, episode=episode))
    remove_download_artifacts(path)
    download = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=episode.id,
        local_media_profile_id=profile.local_media_profile_id,
        download_profile_id=profile.id,
        download_status=MediaDownloadStatus.PENDING.value,
        file_path=path,
        progress=0,
        is_redownload_attempt=False,
    )
    s.add(download)
    s.flush()
    return RedownloadTarget(
        media_download_id=download.id,
        attempt_generation=download.attempt_generation,
        episode_title=episode.title,
    )


def _prepare_redownloads(
        s: Session,
        targets: list[tuple[Episode, DownloadProfileBase]],
) -> list[RedownloadTarget]:
    prepared: list[RedownloadTarget] = []
    for episode, profile in targets:
        existing = s.scalar(
            select(EpisodeMediaDownload).where(
                EpisodeMediaDownload.media_item_id == episode.id,
                EpisodeMediaDownload.local_media_profile_id == profile.local_media_profile_id,
            )
        )
        if existing is None:
            prepared.append(_create_download(s, episode=episode, profile=profile))
            s.commit()
            continue

        # download_episode holds the same lock for the lifetime of an attempt.
        # Waiting here means we never delete a file while an older worker is still
        # writing it. The generation bump then invalidates any queued stale attempt.
        s.commit()
        with serialize_download_attempt(existing.id):
            s.expire_all()
            current = s.get(EpisodeMediaDownload, existing.id)
            if current is None:
                prepared.append(_create_download(s, episode=episode, profile=profile))
            else:
                prepared.append(
                    _reset_existing_download(s, current, episode=episode, profile=profile)
                )
            s.commit()
    return prepared


def _latest_download_task_status(
        s: Session,
        *,
        media_download_id: int,
        attempt_generation: int,
) -> TaskStatus | None:
    runs = s.execute(
        select(TaskRun)
        .join(TaskDefinition, TaskDefinition.id == TaskRun.definition_id)
        .where(TaskDefinition.key == "download_episode")
        .order_by(TaskRun.started_at.desc(), TaskRun.id.desc())
    ).scalars()
    for run in runs:
        inputs = run.meta.get("inputs") if isinstance(run.meta, dict) else None
        if not isinstance(inputs, dict):
            continue
        if inputs.get("media_download_id") != media_download_id:
            continue
        if inputs.get("attempt_generation") != attempt_generation:
            continue
        return run.status if isinstance(run.status, TaskStatus) else TaskStatus(run.status)
    return None


def _check_targets(s: Session, targets: list[RedownloadTarget]) -> tuple[int, str | None]:
    completed = 0
    for target in targets:
        download = s.get(EpisodeMediaDownload, target.media_download_id)
        if download is None:
            return completed, f"Download for '{target.episode_title}' was removed"
        if download.attempt_generation != target.attempt_generation:
            return completed, f"Download for '{target.episode_title}' was restarted by another action"
        if download.download_status in _COMPLETED_STATUSES:
            completed += 1
            continue
        if download.download_status == MediaDownloadStatus.CANCELLED.value:
            return completed, f"Download for '{target.episode_title}' was cancelled"
        if download.download_status == MediaDownloadStatus.ERROR.value:
            task_status = _latest_download_task_status(
                s,
                media_download_id=target.media_download_id,
                attempt_generation=target.attempt_generation,
            )
            if task_status == TaskStatus.FAILED:
                return completed, f"Download for '{target.episode_title}' failed"
            if task_status == TaskStatus.CANCELED:
                return completed, f"Download for '{target.episode_title}' was cancelled"
    return completed, None


async def run_redownload_show_episodes_worker(
        s: Session,
        *,
        show_id: int | None,
        download_profile_id: int | None = None,
        progress=None,
) -> None:
    if show_id is None:
        raise ValueError("Show id is required")

    show = s.get(Show, show_id)
    if show is None:
        raise ValueError(f"Show {show_id} no longer exists")

    profiles = _selected_profiles(
        s,
        show_id=show.id,
        download_profile_id=download_profile_id,
    )
    if not profiles:
        update_progress(progress, 100, "No Download Profiles are attached to this show")
        return

    episode_profiles = _target_episode_profiles(s, profiles)
    if not episode_profiles:
        update_progress(progress, 100, "No eligible episodes to re-download")
        return

    update_progress(progress, 1, f"Preparing {len(episode_profiles)} episode download(s)")
    targets = _prepare_redownloads(s, episode_profiles)

    # Let the normal global queue enforce max_concurrent_downloads. Each episode
    # worker backfills the next pending slot when it finishes, so this master task
    # can simply watch the exact generations it prepared.
    trigger_next_pending_downloads(s)
    total = len(targets)

    while True:
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
        # End the previous read transaction so every poll observes child-worker
        # commits on SQLite as well as on databases with snapshot isolation.
        s.rollback()
        s.expire_all()
        completed, failure = _check_targets(s, targets)
        if failure:
            raise RuntimeError(failure)
        if completed >= total:
            update_progress(progress, 100, f"Re-downloaded {total} episode file(s)")
            return

        percentage = max(1, min(99, int(completed / total * 100)))
        update_progress(
            progress,
            percentage,
            f"Re-downloaded {completed}/{total} episode file(s)",
        )
