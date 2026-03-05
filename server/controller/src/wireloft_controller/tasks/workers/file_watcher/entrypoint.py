from __future__ import annotations

from typing import Optional

from backend.app import db_session
from wireloft_controller.tasks.workers.file_watcher.service import run_file_watcher

## TODO, triggers:
## TODO 1. when file changes are detected in the monitored directories


@scheduler.trigger(
    trigger_type="worker",
    cron="*/10 * * * *",
)
@scheduler.trigger.event(
    event_key="file_change",
)
@scheduler.job(
    key="file_watcher",
    title="Watch local files",
    description="Watch local files to keep them in sync with WireLoft database.",
    default_max_retries=5,
    tracks_progress=False,
)
async def file_watcher() -> None:
    with db_session() as s:
        await run_file_watcher(s)