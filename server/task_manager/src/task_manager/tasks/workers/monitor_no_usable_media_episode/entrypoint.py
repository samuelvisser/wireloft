from __future__ import annotations

from typing import Optional

from config import get_settings
from controller.db_utils import db_session
from task_manager.scheduler.registry import on_cron, on_event, task
from .service import run_monitor_no_usable_media_episode


@on_event(event_name="app.startup", resource_type="show")
@on_cron(
    cron=get_settings().new_episode_schedule.monitor_no_usable_media_episode_cron,
    resource_type="show",
    resource_id=0,
    coalesce=True,
)
@task(
    key="monitor_no_usable_media_episode",
    title="Monitor no-usable-media episodes",
    description="Verify quarantined episodes, recover usable media and delete only confirmed 404s after the grace period.",
    allowed_resource_types=("show",),
    default_max_retries=2,
    tracks_progress=True,
)
async def monitor_no_usable_media_episode(
    *,
    resource_id: Optional[int] = None,
    slug: Optional[str] = None,
    episode_id: Optional[int] = None,
    force: bool = False,
    progress=None,
) -> None:
    settings = get_settings()
    show_id = None if resource_id in {None, 0} else resource_id
    with db_session() as s:
        await run_monitor_no_usable_media_episode(
            s,
            show_id=show_id,
            show_slug=slug,
            episode_id=episode_id,
            force=force,
            delete_after_minutes=settings.episode_status_timing.no_usable_media_delete_after_minutes,
            progress=progress,
        )
