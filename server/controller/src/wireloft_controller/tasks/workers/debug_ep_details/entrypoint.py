from __future__ import annotations

from typing import Optional

from backend.app import db_session
from wireloft_controller.tasks.workers.debug_ep_details.service import run_debug_ep_details
from wireloft_motherboard.scheduler.registry import task


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