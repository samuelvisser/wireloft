from __future__ import annotations

from controller.db_utils import db_session
from task_manager.scheduler.registry import on_event, task
from task_manager.scheduler.results import TaskResult
from task_manager.tasks.helpers.episodes.events import EPISODE_IDENTIFIER_CHANGED_EVENT
from .service import run_rename_file_worker


@on_event(EPISODE_IDENTIFIER_CHANGED_EVENT, resource_type="episode")
@task(
    key="rename_file_worker",
    title="Rename episode file",
    description="Rename existing episode files to match their current output templates and metadata.",
    allowed_resource_types=("episode",),
    default_max_retries=2,
    tracks_progress=True,
)
async def rename_file_worker(
        *,
        resource_id: int | None = None,
        progress=None,
        download_profile_id: int | None = None,
        local_media_profile_id: int | None = None,
        identifier_fields_only: bool = False,
) -> TaskResult:
    """Rename the existing files for one episode in the requested profile scope."""
    if resource_id is None:
        raise ValueError("Rename File requires an episode resource")

    with db_session() as s:
        return await run_rename_file_worker(
            s,
            episode_id=resource_id,
            download_profile_id=download_profile_id,
            local_media_profile_id=local_media_profile_id,
            identifier_fields_only=identifier_fields_only,
            progress=progress,
        )
