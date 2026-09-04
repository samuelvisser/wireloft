from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy.orm import Session

from backend.db.models import Show
from task_manager.tasks.helpers.progress import update_progress
from task_manager.tasks.workers.download_profile_worker._helpers import trigger_next_pending_downloads
from ._helpers import _selected_profiles, _target_episode_profiles, _prepare_redownloads, _POLL_INTERVAL_SECONDS, _check_targets


async def run_redownload_show_episodes_worker(
        s: Session,
        *,
        show_id: int | None,
        download_profile_id: int | None = None,
        progress=None,
) -> dict[str, Any]:
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
    base_result: dict[str, Any] = {
        "show_id": show.id,
        "show_slug": show.slug,
        "show_title": show.title,
        "download_profiles": len(profiles),
    }
    if not profiles:
        update_progress(progress, 100, "No Download Profiles are attached to this show")
        return {**base_result, "episode_files": 0}

    episode_profiles = _target_episode_profiles(s, profiles)
    if not episode_profiles:
        update_progress(progress, 100, "No eligible episodes to re-download")
        return {**base_result, "episode_files": 0}

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
            return {**base_result, "episode_files": total}

        percentage = max(1, min(99, int(completed / total * 100)))
        update_progress(
            progress,
            percentage,
            f"Re-downloaded {completed}/{total} episode file(s)",
        )
