from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy.orm import Session

from backend.db.models import Episode, Show
from dailywire_downloader import DownloadCancelled
from task_manager.tasks.helpers.progress import update_progress
from ._helpers import (
    _POLL_INTERVAL_SECONDS,
    _cancel_targets,
    _check_targets,
    _prepare_redownloads,
    _selected_downloads,
)


async def run_redownload_show_episodes_worker(
        s: Session,
        *,
        show_id: int | None = None,
        episode_id: int | None = None,
        local_media_profile_id: int | None = None,
        progress=None,
) -> dict[str, Any]:
    """Coordinate replacement downloads for existing episode media rows."""
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

    downloads = _selected_downloads(
        s,
        show_id=show.id,
        episode_id=episode.id if episode is not None else None,
        local_media_profile_id=local_media_profile_id,
    )
    profile_count = len({download.local_media_profile_id for download in downloads})
    base_result: dict[str, Any] = {
        "show_id": show.id,
        "show_slug": show.slug,
        "show_title": show.title,
        "local_media_profiles": profile_count,
    }
    if episode is not None:
        base_result.update({
            "episode_id": episode.id,
            "episode_slug": episode.slug,
            "episode_title": episode.title,
        })

    if not downloads:
        update_progress(progress, 100, "No downloaded episodes match this request")
        return {**base_result, "episode_files": 0}

    update_progress(progress, 1, f"Preparing {len(downloads)} episode download(s)")
    targets = _prepare_redownloads(s, downloads)
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
