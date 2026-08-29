from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from backend.db.models import Episode, PodcastDownloadProfile
from task_manager.scheduler.executor import trigger_now
from task_manager.tasks.helpers.progress import update_progress

from ._helpers import (
    cleanup_older_episodes,
    ensure_episode_download,
    get_download_profile_episodes,
    remaining_download_budget,
    resolve_target_profiles,
)


async def run_download_profile_worker(
        s: Session, *, resource_id: Optional[int] = None, resource_type: Optional[str] = None, progress=None
) -> None:
    """Make sure every enabled Download Profile's episodes are being downloaded.

    Scope depends on how the run was triggered: a single episode going final (or
    countdown-published) only checks that episode against its show's profiles; a
    freshly indexed show, a manual "run this show/profile" trigger, or the periodic
    verification cron/app-startup sweep all fall through to a full re-check of the
    profile(s) in scope, which also runs the podcast "delete older episodes"
    cleanup.
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
            print("download_profile_worker completed: episode not found")
            return

    budget = remaining_download_budget(s)
    triggered = 0
    deferred = 0
    total = len(profiles)

    for index, profile in enumerate(profiles):
        for episode in get_download_profile_episodes(s, profile, only_episode=only_episode):
            action = ensure_episode_download(s, profile, episode)
            s.commit()

            if not action.needs_trigger:
                continue
            if budget <= 0:
                deferred += 1
                continue

            trigger_now(
                def_key="download_episode",
                resource_type="episode",
                resource_id=episode.id,
                media_download_id=action.media_download_id,
                is_redownload=action.is_redownload,
            )
            budget -= 1
            triggered += 1

        # Cleanup is a profile-wide reconciliation step; skip it for single-episode
        # runs so a burst of publish events doesn't repeatedly re-scan the show.
        if only_episode is None and isinstance(profile, PodcastDownloadProfile):
            removed = cleanup_older_episodes(s, profile)
            if removed:
                s.commit()

        update_progress(
            progress,
            int((index + 1) / total * 100),
            f"Queued {triggered} download(s) so far ({index + 1}/{total} profile(s) checked)",
        )

    message = f"Queued {triggered} download(s)"
    if deferred:
        message += f"; {deferred} left pending (concurrent download limit reached)"
    update_progress(progress, 100, message)
    print(f"download_profile_worker completed: {message}")
