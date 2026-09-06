from __future__ import annotations

from controller.db_utils import db_session
from task_manager.scheduler.registry import task
from task_manager.scheduler.results import TaskResult

from .service import run_redownload_show_episodes_worker


@task(
    key="redownload_show_episodes_worker",
    title="Re-download show episodes",
    description="Deletes existing episode files for selected Local Media Profiles and downloads them again.",
    allowed_resource_types=("show",),
    default_max_retries=0,
    tracks_progress=True,
)
async def redownload_show_episodes_worker(
        *,
        resource_id: int | None = None,
        progress=None,
        local_media_profile_id: int | None = None,
) -> TaskResult:
    """Run one explicitly requested show re-download operation."""
    with db_session() as s:
        result = await run_redownload_show_episodes_worker(
            s,
            show_id=resource_id,
            local_media_profile_id=local_media_profile_id,
            progress=progress,
        )

    count = int(result.get("episode_files", 0))
    profile_count = int(result.get("local_media_profiles", 0))
    show_title = str(result.get("show_title") or "show")
    return TaskResult(
        summary=(
            f"Re-download finished for {show_title}: "
            f"{count} episode {'file' if count == 1 else 'files'} re-downloaded"
        ),
        data={
            **result,
            "episode_files": count,
            "local_media_profiles": profile_count,
        },
    )
