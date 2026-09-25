from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from typing import Any

from sqlalchemy.orm import Session

from backend.utils.episode_download_scope import EpisodeDownloadScope
from dailywire_downloader import DownloadCancelled
from task_manager.tasks.helpers.progress import update_progress
from task_manager.tasks.helpers.custom_index_readiness import (
    custom_index_pair_lock, pair_is_ready, wait_for_custom_index_pair,
)
from ._helpers import (
    _POLL_INTERVAL_SECONDS,
    _cancel_targets,
    _check_targets,
    _prepare_redownloads,
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
    scope = EpisodeDownloadScope.resolve(
        s,
        show_id=show_id,
        episode_id=episode_id,
    ).select(local_media_profile_id=local_media_profile_id)
    pairs = {(download.media.show_id, download.local_media_profile_id) for download in scope.downloads}
    s.rollback()
    while True:
        for pair in sorted(pairs):
            await wait_for_custom_index_pair(*pair)
        async with AsyncExitStack() as locks:
            for pair in sorted(pairs):
                await locks.enter_async_context(custom_index_pair_lock(*pair))
            if not all(pair_is_ready(*pair) for pair in pairs):
                continue
            scope = EpisodeDownloadScope.resolve(
                s, show_id=show_id, episode_id=episode_id,
            ).select(local_media_profile_id=local_media_profile_id)
            base_result = scope.result_data()
            downloads = list(scope.downloads)

            if not downloads:
                update_progress(progress, 100, "No downloaded episodes match this request")
                return {**base_result, "episode_files": 0}

            update_progress(progress, 1, f"Preparing {len(downloads)} episode download(s)")
            targets = _prepare_redownloads(s, downloads)
            break
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
