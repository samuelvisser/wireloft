from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from backend.db.models import Episode, PodcastDownloadProfile
from task_manager.scheduler.types import OperationSource
from task_manager.tasks.helpers.progress import update_progress
from task_manager.tasks.media_download_operations import (
    create_media_download_operation,
    dispatch_queued_media_download_operations,
)

from ._helpers import (
    cleanup_older_episodes,
    ensure_episode_download,
    get_download_profile_episodes,
    resolve_target_profiles,
)


async def run_download_profile_worker(
        s: Session, *, resource_id: Optional[int] = None, resource_type: Optional[str] = None, progress=None
) -> None:
    """Reconcile Download Profile domain state and create SYSTEM download operations.

    The profile worker no longer maintains or starts a second download queue. It
    creates/reuses persistent MediaDownload artifact rows and represents every
    required attempt as a normal ``media.download`` TaskOperation. The shared
    operation dispatcher enforces the configured download concurrency limit.
    """
    print("Starting download_profile_worker" + (f" ({resource_type}={resource_id})" if resource_type else ""))

    profiles = resolve_target_profiles(s, resource_type=resource_type, resource_id=resource_id)
    if not profiles:
        update_progress(progress, 100, "No enabled download profile in scope")
        print("download_profile_worker completed: nothing to do")
        return

    only_episode: Optional[Episode] = None
    if resource_type == "episode" and resource_id is not None:
        only_episode = s.get(Episode, resource_id)
        if only_episode is None:
            update_progress(progress, 100, f"Episode {resource_id} no longer exists")
            return

    created = 0
    total = len(profiles)
    for index, profile in enumerate(profiles):
        for episode in get_download_profile_episodes(s, profile, only_episode=only_episode):
            action = ensure_episode_download(s, profile, episode)
            if not action.needs_operation:
                continue

            download = s.get(__import__(
                "backend.db.models.media_download",
                fromlist=["MediaDownloadBase"],
            ).MediaDownloadBase, action.media_download_id)
            if download is None:
                continue
            create_media_download_operation(
                s,
                download,
                source=OperationSource.SYSTEM.value,
                is_redownload=action.is_redownload,
            )
            created += 1

        if isinstance(profile, PodcastDownloadProfile):
            should_cleanup = only_episode is None or profile.download_episode_count > 0
            if should_cleanup:
                cleanup_older_episodes(s, profile)

        # Keep each profile reconciliation transaction short. The operations are
        # durable but remain QUEUED until the shared dispatcher below has room.
        s.commit()
        update_progress(
            progress,
            int((index + 1) / total * 90),
            f"Prepared {created} download operation(s) ({index + 1}/{total} profile(s) checked)",
        )

    dispatched = dispatch_queued_media_download_operations(s)
    s.commit()

    message = f"Prepared {created} download operation(s)"
    if dispatched:
        message += f"; started {dispatched} queued download(s)"
    update_progress(progress, 100, message)
    print(f"download_profile_worker completed: {message}")
