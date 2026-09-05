from __future__ import annotations

from typing import Optional

from controller.db_utils import db_session
from task_manager.scheduler.registry import task
from task_manager.tasks.media_download_operations import on_media_download_task_terminal
from task_manager.tasks.workers.download_attempt import serialize_download_attempt
from .service import run_download_episode


@task(
    key="download_episode",
    title="Download episode media",
    description="Downloads one episode's audio or video according to a Local Media Profile.",
    allowed_resource_types=("media_download",),
    default_max_retries=2,
    tracks_progress=True,
    terminal_callback=on_media_download_task_terminal,
    recovery_dispatcher=on_media_download_task_terminal,
)
async def download_episode(
        *,
        resource_id: Optional[int] = None,
        is_redownload: bool = False,
        progress=None,
):
    """Execute one MediaDownload artifact attempt.

    ``resource_id`` is the MediaDownload id. All changing execution state is
    owned by the TaskRun/TaskOperation that invoked this worker; the MediaDownload
    row contains only persistent artifact facts.
    """
    if resource_id is None:
        raise ValueError("A MediaDownload resource ID is required")

    with serialize_download_attempt(resource_id):
        with db_session() as session:
            return await run_download_episode(
                session,
                media_download_id=resource_id,
                is_redownload=is_redownload,
                progress=progress,
            )
