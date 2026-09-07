from __future__ import annotations

from typing import Optional

from controller.db_utils import db_session
from task_manager.scheduler.registry import task
from .service import run_monitor_pending_episode


@task(
    key="monitor_pending_episode",
    title="Monitor pending episode",
    description="Monitor a scheduled, delayed, live, processing or countdown episode until ownership transfers.",
    allowed_resource_types=("episode",),
    default_max_retries=5,
    tracks_progress=False,
)
async def monitor_pending_episode(
    *,
    resource_id: Optional[int] = None,
    slug: Optional[str] = None,
    progress=None,
    show_slug: Optional[str] = None,
    show_id: Optional[int] = None,
    season_id: Optional[int] = None,
    episode_identifier: Optional[str] = None,
    episode_index: Optional[int] = None,
) -> None:
    del progress
    with db_session() as s:
        await run_monitor_pending_episode(
            s,
            episode_id=resource_id,
            episode_slug=slug,
            show_id=show_id,
            show_slug=show_slug,
            season_id=season_id,
            episode_identifier=episode_identifier,
            episode_index=episode_index,
        )
