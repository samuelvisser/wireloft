from __future__ import annotations

from controller.db_utils import db_session
from task_manager.scheduler.registry import task, on_cron, on_event
from .service import run_file_watcher


@task(
    key="file_watcher",
    title="Watch local files",
    description="Watch local files to keep them in sync with WireLoft database.",
    allowed_resource_types=("show",),
    default_max_retries=5,
    tracks_progress=False,
)
@on_cron(
    cron="*/10 * * * *",
    resource_type="show",
    resource_id=0,
    coalesce=True,
)
@on_event(
    event_name="file.changed",
    resource_type="show",
)
async def file_watcher(*, resource_id=None, progress=None) -> None:
    with db_session() as s:
        await run_file_watcher(s)
