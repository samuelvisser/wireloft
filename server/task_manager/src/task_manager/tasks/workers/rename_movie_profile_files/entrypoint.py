from __future__ import annotations

from controller.db_utils import db_session
from task_manager.scheduler.registry import task
from task_manager.scheduler.results import TaskResult

from .service import run_rename_movie_profile_files


@task(
    key="rename_movie_profile_files",
    title="Rename movie profile files",
    description="Plan and safely rename every movie file for one Local Media Profile.",
    allowed_resource_types=("local_media_profile",),
    default_max_retries=2,
    tracks_progress=True,
)
async def rename_movie_profile_files(
        *,
        resource_id: int | None = None,
        progress=None,
) -> TaskResult:
    if resource_id is None:
        raise ValueError("Movie File Rename requires a Local Media Profile")

    with db_session() as session:
        return run_rename_movie_profile_files(
            session,
            local_media_profile_id=resource_id,
            progress=progress,
        )
