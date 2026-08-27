from __future__ import annotations

from controller.db_utils import db_session
from task_manager.scheduler.registry import task, on_event
from .service import run_resume_interrupted_downloads


@on_event(
    event_name="app.startup",
    resource_type="download_profile",
)
@task(
    key="resume_interrupted_downloads",
    title="Resume interrupted downloads",
    description="Requeues any download left stuck DOWNLOADING by an unclean shutdown",
    allowed_resource_types=("download_profile",),
    default_max_retries=1,
    tracks_progress=True,
)
async def resume_interrupted_downloads(*, resource_id=None, progress=None) -> None:
    """Reset any download stuck DOWNLOADING from before this startup and requeue it.

    Runs once on app.startup, before download_profile_worker's own startup
    sweep: a row can only legitimately be DOWNLOADING while a worker in this
    process is running it, and nothing has started one yet this early, so
    any row still in that state was orphaned by an unclean shutdown.
    """
    with db_session() as s:
        await run_resume_interrupted_downloads(s, progress=progress)
