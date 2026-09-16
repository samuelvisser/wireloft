from __future__ import annotations

from controller.db_utils import db_session
from task_manager.scheduler.registry import task
from task_manager.scheduler.results import TaskResult

from .service import run_delete_show_downloads_worker


@task(
    key="delete_show_downloads_worker",
    title="Delete show downloads",
    description="Deletes selected episode files without downloading replacements.",
    allowed_resource_types=("show",),
    default_max_retries=0,
    tracks_progress=True,
)
async def delete_show_downloads_worker(
        *,
        resource_id: int | None = None,
        progress=None,
        local_media_profile_id: int | None = None,
) -> TaskResult:
    """Run an explicitly requested show-wide download deletion."""
    if resource_id is None:
        raise ValueError("Delete show downloads requires a show resource")

    with db_session() as s:
        result = run_delete_show_downloads_worker(
            s,
            show_id=resource_id,
            local_media_profile_id=local_media_profile_id,
            progress=progress,
        )

    count = int(result.get("episode_files", 0))
    profile_count = int(result.get("local_media_profiles", 0))
    target_title = str(result.get("show_title") or "show")
    return TaskResult(
        summary=(
            f"Deleted downloads for {target_title}: "
            f"{count} episode {'file' if count == 1 else 'files'} deleted"
        ),
        data={
            **result,
            "episode_files": count,
            "local_media_profiles": profile_count,
        },
    )
