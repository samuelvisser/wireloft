from __future__ import annotations

from backend.api.endpoints.shows.service import SHOW_REDOWNLOAD_EPISODES_REQUESTED_EVENT
from controller.db_utils import db_session
from task_manager.scheduler.registry import on_event, task

from .service import run_redownload_show_episodes_worker


@on_event(SHOW_REDOWNLOAD_EPISODES_REQUESTED_EVENT, resource_type="show")
@task(
    key="redownload_show_episodes_worker",
    title="Re-download show episodes",
    description="Deletes episode files for selected Download Profiles and downloads them again.",
    allowed_resource_types=("show",),
    default_max_retries=0,
    tracks_progress=True,
)
async def redownload_show_episodes_worker(
        *,
        resource_id: int | None = None,
        progress=None,
        download_profile_id: int | None = None,
        manual_request_id: str | None = None,
) -> None:
    """Run one explicitly requested show re-download operation.

    ``manual_request_id`` is intentionally accepted even though the worker does
    not need its value. The task executor persists inputs, allowing the UI to
    correlate this durable TaskRun with the action that started it.
    """
    del manual_request_id
    with db_session() as s:
        await run_redownload_show_episodes_worker(
            s,
            show_id=resource_id,
            download_profile_id=download_profile_id,
            progress=progress,
        )
