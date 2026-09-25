from __future__ import annotations

from controller.db_utils import db_session
from task_manager.tasks.helpers.custom_index_readiness import (
    custom_index_pair_lock, pair_is_ready, request_missing_index_repair,
    wait_for_custom_index_pair,
)
from backend.utils.custom_index import CustomIndexNotReadyError
from task_manager.scheduler.registry import task
from task_manager.scheduler.results import TaskResult

from .service import run_rename_show_profile_files


@task(
    key="rename_show_profile_files",
    title="Rename show files",
    description="Plan and safely rename one show's files for one Local Media Profile.",
    allowed_resource_types=("show",),
    default_max_retries=2,
    tracks_progress=True,
)
async def rename_show_profile_files(
    *,
    resource_id: int | None = None,
    progress=None,
    local_media_profile_id: int | None = None,
    episode_ids: list[int] | None = None,
    expected_sources: dict[str, str] | None = None,
) -> TaskResult:
    if resource_id is None or local_media_profile_id is None:
        raise ValueError("Batch File Rename requires a Show and Local Media Profile")
    try:
        while True:
            await wait_for_custom_index_pair(resource_id, local_media_profile_id)
            async with custom_index_pair_lock(resource_id, local_media_profile_id):
                if not pair_is_ready(resource_id, local_media_profile_id):
                    continue
                with db_session() as session:
                    return run_rename_show_profile_files(
                        session,
                        show_id=resource_id,
                        local_media_profile_id=local_media_profile_id,
                        episode_ids=episode_ids,
                        expected_sources=expected_sources,
                        progress=progress,
                    )
    except CustomIndexNotReadyError as exc:
        request_missing_index_repair(exc)
        raise
