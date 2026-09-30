from __future__ import annotations

from sqlalchemy.orm import Session
from backend.utils.episode_download_scope import EpisodeDownloadScope
from task_manager.scheduler.results import TaskResult
from task_manager.tasks.download_batch import run_download_batch


async def run_redownload_show_episodes_worker(
    s: Session, *, show_id: int | None = None, episode_id: int | None = None,
    local_media_profile_id: int | None = None, progress=None,
) -> TaskResult:
    scope = EpisodeDownloadScope.resolve(s, show_id=show_id, episode_id=episode_id).select(local_media_profile_id=local_media_profile_id)
    context = scope.result_data()
    ids = [download.id for download in scope.downloads]
    s.rollback()
    result = await run_download_batch(ids, progress=progress, force_new=True)
    return TaskResult(result.summary, {**context, **result.data, "episode_files": result.data["downloads_completed"]}, outcome=result.outcome)
