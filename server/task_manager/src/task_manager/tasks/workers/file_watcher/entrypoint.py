from __future__ import annotations

from typing import Optional

from config import get_settings
from controller.db_utils import db_session
from task_manager.scheduler.registry import task, on_cron, on_event
from .service import run_file_watcher


@on_event(
    event_name="app.startup",
    resource_type="show",
)
@on_cron(
    cron=get_settings().file_watcher.scan_cron,
    resource_type="show",
    resource_id=0,
    coalesce=True,
)
@task(
    key="file_watcher",
    title="Watch local files",
    description="Watch local files to keep them in sync with WireLoft database.",
    allowed_resource_types=("show",),
    default_max_retries=5,
    tracks_progress=False,
)
async def file_watcher(*, resource_id: Optional[int] = None, slug: Optional[str] = None, progress=None) -> None:
    """
    Reconciles downloaded episode files on disk with the WireLoft database.

    Parameters:
    resource_id : Optional[int]
        The ID of a specific show if the scan needs to focus on one.
    slug : Optional[str]
        The slug of a specific show if the scan needs to focus on one.
    progress : Any
        A progress tracker object.
    """
    with db_session() as s:
        await run_file_watcher(s, show_id=resource_id, show_slug=slug, progress=progress)
