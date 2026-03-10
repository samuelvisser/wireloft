from __future__ import annotations

from typing import Optional

from controller.db_utils import db_session
from task_manager.tasks.workers.debug_ep_details.service import run_debug_ep_details
from task_manager.scheduler.registry import task


@task(
    key="debug_ep_details",
    title="Debug episode details",
    description="Debugs episode details for the given show.",
    allowed_resource_types=("shows",),
    default_max_retries=5,
    tracks_progress=False,
)
async def debug_ep_details(*, resource_id: Optional[int] = None, slug: Optional[str] = None, progress):
    with db_session() as s:
        await run_debug_ep_details(s, show_slug=slug, progress=progress)