from __future__ import annotations

from typing import Optional

from config import get_settings
from controller.db_utils import db_session
from task_manager.scheduler.registry import task, on_cron, on_event
from .service import run_check_episodes_stuck_at_dw_processing


@on_event(
    event_name="app.startup",
    resource_type="show",
)
@on_cron(
    # Keep the existing setting name for config.yml/environment compatibility;
    # its responsibility is now the broader stuck-processing cleanup.
    cron=get_settings().new_episode_schedule.check_no_show_today_cron,
    resource_type="show",
    resource_id=0,
    coalesce=True,
)
@task(
    key="check_episodes_stuck_at_dw_processing",
    title="Check stuck Daily Wire episodes",
    description=(
        "Deletes No Show Today placeholders and continuously missing Daily Wire "
        "episodes after a four-hour processing grace period"
    ),
    allowed_resource_types=("show",),
    default_max_retries=2,
    tracks_progress=True,
)
async def check_episodes_stuck_at_dw_processing(
        *,
        resource_id: Optional[int] = None,
        slug: Optional[str] = None,
        progress=None,
) -> None:
    """Clean up unusable episodes that remain in dw_processing for too long."""
    with db_session() as s:
        await run_check_episodes_stuck_at_dw_processing(
            s,
            show_id=resource_id,
            show_slug=slug,
            progress=progress,
        )
