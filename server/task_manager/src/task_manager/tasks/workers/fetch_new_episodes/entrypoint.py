from __future__ import annotations

from typing import Optional

from config import get_settings
from controller.db_utils import db_session
from task_manager.scheduler.registry import task, on_cron, on_event
from task_manager.scheduler.results import TaskResult
from .service import run_fetch_new_episodes


@on_event(
    event_name="app.startup",
    resource_type="show",
)
@on_event(
    event_name="show.added",
    resource_type="show",
)
@on_event(
    event_name="show.sync_requested",
    resource_type="show",
)
@on_cron(
    cron=get_settings().new_episode_schedule.find_episodes_cron,
    resource_type="show",
    resource_id=0,
    coalesce=True,
)
@task(
    key="fetch_new_episodes",
    title="Find new episodes in all shows",
    description="Finds new episodes in all shows.",
    allowed_resource_types=("show",),
    default_max_retries=5,
    tracks_progress=True,
)
async def fetch_new_episodes(
    *,
    resource_id: Optional[int] = None,
    slug: Optional[str] = None,
    dry_run: bool = False,
    progress=None,
) -> TaskResult:
    """Delegate episode discovery to the worker service."""
    with db_session() as s:
        result = await run_fetch_new_episodes(
            s,
            show_id=resource_id,
            show_slug=slug,
            dry_run=dry_run,
            progress=progress,
        )

    return TaskResult(
        summary=result.summary(),
        data=result.as_data(),
    )
