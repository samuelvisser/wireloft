from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from backend.db.models import DownloadProfileBase, Episode, PodcastDownloadProfile
from backend.db.models.media_download import MediaDownloadBase
from task_manager.scheduler.types import OperationSource
from task_manager.tasks.helpers.download_profiles import lock_enabled_download_profile
from task_manager.tasks.helpers.custom_index_readiness import wait_for_custom_index_pair
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

    Each profile reconciliation owns a lock on that Download Profile until its
    operation rows are committed. A concurrent profile disable therefore cannot
    interleave with a stale in-memory profile and recreate downloads after the
    disable has taken effect.
    """
    print("Starting download_profile_worker" + (f" ({resource_type}={resource_id})" if resource_type else ""))

    profiles = resolve_target_profiles(s, resource_type=resource_type, resource_id=resource_id)
    profile_ids = tuple(profile.id for profile in profiles)

    # Profile discovery is advisory only. End that read transaction before taking
    # the per-profile reconciliation lock so the enabled state is re-read fresh.
    s.rollback()

    if not profile_ids:
        update_progress(progress, 100, "No enabled download profile in scope")
        print("download_profile_worker completed: nothing to do")
        return

    only_episode_id = resource_id if resource_type == "episode" and resource_id is not None else None
    created = 0
    total = len(profile_ids)

    for index, profile_id in enumerate(profile_ids):
        pending_profile = s.get(DownloadProfileBase, profile_id)
        pair = (pending_profile.show_id, pending_profile.local_media_profile_id) if pending_profile is not None else None
        s.rollback()
        if pair is not None:
            await wait_for_custom_index_pair(*pair)
        profile = lock_enabled_download_profile(s, profile_id)
        if profile is None:
            # Release the lock acquired while confirming the profile is disabled.
            s.rollback()
            update_progress(
                progress,
                int((index + 1) / total * 90),
                f"Prepared {created} download operation(s) ({index + 1}/{total} profile(s) checked)",
            )
            continue

        only_episode: Optional[Episode] = None
        if only_episode_id is not None:
            only_episode = s.get(Episode, only_episode_id)
            if only_episode is None:
                s.rollback()
                update_progress(progress, 100, f"Episode {only_episode_id} no longer exists")
                return

        for episode in get_download_profile_episodes(s, profile, only_episode=only_episode):
            action = ensure_episode_download(s, profile, episode)
            if not action.needs_operation:
                continue

            download = s.get(MediaDownloadBase, action.media_download_id)
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

        # The profile lock is held through this commit. A concurrent disable can
        # only proceed after every operation created from this enabled snapshot is
        # durable; once disabled, later worker runs will skip the profile entirely.
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
