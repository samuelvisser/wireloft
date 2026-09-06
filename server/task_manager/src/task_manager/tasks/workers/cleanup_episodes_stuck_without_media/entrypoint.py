from __future__ import annotations

from typing import Optional

from config import get_settings
from controller.db_utils import db_session
from task_manager.scheduler.registry import task, on_cron, on_event
from .service import run_cleanup_episodes_stuck_without_media


@on_event(
    event_name="app.startup",
    resource_type="show",
)
@on_cron(
    cron=get_settings().new_episode_schedule.cleanup_episodes_stuck_without_media_cron,
    resource_type="show",
    resource_id=0,
    coalesce=True,
)
@task(
    key="cleanup_episodes_stuck_without_media",
    title="Clean up episodes stuck without media",
    description=(
        "Deletes No Show Today placeholders and continuously missing Daily Wire "
        "episodes after the configured cleanup delay"
    ),
    allowed_resource_types=("show",),
    default_max_retries=2,
    tracks_progress=True,
)
async def cleanup_episodes_stuck_without_media(
        *,
        resource_id: Optional[int] = None,
        slug: Optional[str] = None,
        episode_id: Optional[int] = None,
        force: bool = False,
        progress=None,
) -> None:
    """Clean up episodes that remain stuck without usable media for too long."""
    settings = get_settings()
    with db_session() as s:
        await run_cleanup_episodes_stuck_without_media(
            s,
            show_id=resource_id,
            show_slug=slug,
            episode_id=episode_id,
            force=force,
            delete_after_minutes=(
                settings.episode_status_timing.dw_processing_delete_after_minutes
            ),
            progress=progress,
        )
