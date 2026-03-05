from __future__ import annotations

from typing import Optional

from wireloft_controller.app import db_session
from wireloft_motherboard.scheduler.registry import task, on_cron, on_event
from .service import run_fetch_new_episodes


@task(
    key="fetch_new_episodes",
    title="Find new episodes in all shows",
    description="Finds new episodes in all shows.",
    allowed_resource_types=("show",),
    default_max_retries=5,
    tracks_progress=False,
)
@on_cron(
    cron="settings:new_episode_schedule.find_episodes_cron",  # Special marker to get from settings
    resource_type="show",
    resource_id=0,  # 0 = all shows
    coalesce=True,  # Don't run multiple times if delayed
    run_on_startup=True,  # Also run on startup to catch up
)
@on_event(
    event_name="show.added",
    resource_type="show",
)
async def fetch_new_episodes(*, resource_id: Optional[int] = None, slug: Optional[str] = None, progress=None) -> None:
    """
    Finds new episodes in all shows.

    This worker searches for new episodes across all shows. It retrieves
    new episodes using the provided parameters and updates the database.

    Parameters:
    resource_id : Optional[int]
        The ID of a specific show if the task needs to focus on one.
    slug : Optional[str]
        The slug of a specific show if the task needs to focus on one.
    progress : Any
        A progress tracker object.

    Raises:
        Any raised exceptions during the execution of the database session
        or async tasks.
    """
    with db_session() as s:
        await run_fetch_new_episodes(s, show_id=resource_id, show_slug=slug, progress=progress)