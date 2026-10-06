from __future__ import annotations

from controller.db_utils import db_session
from task_manager.scheduler.registry import on_event, task
from task_manager.scheduler.results import TaskResult

from .service import run_finalize_countdown_downloads


@on_event("app.startup", resource_type="episode")
@on_event("episode.published_final", resource_type="episode")
@task(
    key="finalize_countdown_downloads",
    title="Replace countdown downloads",
    description="Replaces episode downloads that were intentionally captured before final media became available.",
    allowed_resource_types=("episode",),
    default_max_retries=5,
    tracks_progress=False,
)
async def finalize_countdown_downloads(
    *,
    resource_id: int | None = None,
    progress=None,
) -> TaskResult:
    del progress
    with db_session() as s:
        return await run_finalize_countdown_downloads(
            s,
            episode_id=resource_id,
        )
