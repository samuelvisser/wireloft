from __future__ import annotations

from typing import Optional

from config import get_settings
from controller.db_utils import db_session
from task_manager.scheduler.registry import task, on_cron, on_event
from .service import run_check_no_show_today_episodes


@on_event(
    event_name="app.startup",
    resource_type="show",
)
@on_cron(
    cron=get_settings().new_episode_schedule.check_no_show_today_cron,
    resource_type="show",
    resource_id=0,
    coalesce=True,
)
@task(
    key="check_no_show_today_episodes",
    title="Check 'No Show Today' episodes",
    description="Deletes local 'No Show Today' placeholder episodes once Daily Wire removes them",
    allowed_resource_types=("show",),
    default_max_retries=2,
    tracks_progress=True,
)
async def check_no_show_today_episodes(*, resource_id: Optional[int] = None, slug: Optional[str] = None, progress=None) -> None:
    """
    Checks known "No Show Today" placeholder episodes against Daily Wire and
    deletes any locally that Daily Wire has since removed.

    Parameters:
    resource_id : Optional[int]
        The ID of a specific show if the task needs to focus on one.
    slug : Optional[str]
        The slug of a specific show if the task needs to focus on one.
    """
    with db_session() as s:
        await run_check_no_show_today_episodes(s, show_id=resource_id, show_slug=slug, progress=progress)
