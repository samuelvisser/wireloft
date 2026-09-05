from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy.orm import Session

from backend.db.models import Episode, Show
from dailywire_downloader import DownloadCancelled
from task_manager.tasks.helpers.progress import update_progress
from task_manager.tasks.workers.download_profile_worker._helpers import get_download_profile_episodes
from ._helpers import (
    _POLL_INTERVAL_SECONDS,
    _cancel_targets,
    _check_targets,
    _prepare_redownloads,
    _selected_profiles,
    _target_episode_profiles,
)


async def run_redownload_show_episodes_worker(
        s: Session,
        *,
        show_id: int | None = None,
        episode_id: int | None = None,
        download_profile_id: int | None = None,
        progress=None,
) -> dict[str, Any]:
    """Coordinate a show-wide or single-episode replacement through child downloads."""
    if (show_id is None) == (episode_id is None):
        raise ValueError("Provide exactly one show id or episode id")

    episode: Episode | None = None
    if episode_id is not None:
        episode = s.get(Episode, episode_id)
        if episode is None:
            raise ValueError(f"Episode {episode_id} no longer exists")
        show = episode.show
    else:
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
    if episode is not None:
        base_result.update({
            "episode_id": episode.id,
            "episode_slug": episode.slug,
            "episode_title": episode.title,
        })

    if not profiles:
        update_progress(progress, 100, "No Download Profiles are attached to this show")
        return {**base_result, "episode_files": 0}

    if episode is None:
        episode_profiles = _target_episode_profiles(s, profiles)
    else:
        episode_profiles = [
            (episode, profile)
            for profile in profiles
            if get_download_profile_episodes(s, profile, only_episode=episode)
        ]

    if not episode_profiles:
        update_progress(progress, 100, "No eligible episodes to re-download")
        return {**base_result, "episode_files": 0}

    update_progress(progress, 1, f"Preparing {len(episode_profiles)} episode download(s)")
    targets = _prepare_redownloads(s, episode_profiles)
    total = len(targets)

    try:
        while True:
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
            if progress is not None and callable(progress) and progress():
                raise DownloadCancelled("Re-download was canceled")

            # End the previous read transaction so every poll observes child
            # TaskOperation commits on SQLite as well as snapshot databases.
            s.rollback()
            s.expire_all()
            completed, aggregate_percent, failure = _check_targets(s, targets)
            if failure:
                raise RuntimeError(failure)
            if completed >= total:
                update_progress(progress, 100, f"Re-downloaded {total} episode file(s)")
                return {**base_result, "episode_files": total}

            update_progress(
                progress,
                max(1, min(99, aggregate_percent)),
                f"Re-downloaded {completed}/{total} episode file(s)",
            )
    except Exception:
        # A canceled/failed parent task must not leave independent child downloads
        # running after the high-level replacement has ended.
        _cancel_targets(targets, reason="Parent re-download stopped")
        raise
