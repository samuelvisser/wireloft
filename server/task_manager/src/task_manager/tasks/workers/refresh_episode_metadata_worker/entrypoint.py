from __future__ import annotations

from controller.db_utils import db_session
from task_manager.scheduler.registry import on_event, task
from .service import run_refresh_episode_metadata_worker


@on_event("app.startup", resource_type="episode")
@on_event("episode.metadata_refresh_requested", resource_type="episode")
@on_event("episode.monitor_completed", resource_type="episode")
@task(
    key="refresh_episode_metadata_worker",
    title="Refresh episode metadata",
    description="Refresh finalized Daily Wire episode metadata while it settles after publication.",
    allowed_resource_types=("episode",),
    default_max_retries=5,
    tracks_progress=False,
)
async def refresh_episode_metadata_worker(
        *,
        resource_id: int | None = None,
        progress=None,
        refresh: bool = False,
        scheduled_offset_seconds: int | None = None,
) -> None:
    """Schedule or execute targeted metadata checks for finalized episodes."""
    with db_session() as s:
        await run_refresh_episode_metadata_worker(
            s,
            episode_id=resource_id,
            refresh=refresh,
            scheduled_offset_seconds=scheduled_offset_seconds,
        )
