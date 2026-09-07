from __future__ import annotations

from controller.db_utils import db_session
from task_manager.scheduler.registry import task
from task_manager.scheduler.results import TaskResult

from .service import run_redownload_show_episodes_worker


@task(
    key="redownload_show_episodes_worker",
    title="Re-download episodes",
    description="Deletes selected episode files and downloads them again.",
    allowed_resource_types=("show", "episode"),
    default_max_retries=0,
    tracks_progress=True,
)
async def redownload_show_episodes_worker(
        *,
        resource_id: int | None = None,
        resource_type: str | None = None,
        progress=None,
        download_profile_id: int | None = None,
) -> TaskResult:
    """Run an explicitly requested show-wide or targeted episode re-download."""
    is_episode = resource_type == "episode"
    with db_session() as s:
        result = await run_redownload_show_episodes_worker(
            s,
            show_id=None if is_episode else resource_id,
            episode_id=resource_id if is_episode else None,
            download_profile_id=download_profile_id,
            progress=progress,
        )

    count = int(result.get("episode_files", 0))
    profile_count = int(result.get("download_profiles", 0))
    target_title = str(
        result.get("episode_title")
        or result.get("show_title")
        or "media"
    )
    return TaskResult(
        summary=(
            f"Re-download finished for {target_title}: "
            f"{count} episode {'file' if count == 1 else 'files'} re-downloaded"
        ),
        data={
            **result,
            "episode_files": count,
            "download_profiles": profile_count,
        },
    )
