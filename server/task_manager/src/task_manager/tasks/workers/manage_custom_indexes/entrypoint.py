from __future__ import annotations

from controller.db_utils import db_session
from backend.db.models import CustomIndexState
from backend.services.custom_indexes import dispatch_custom_index_reconciliation
from sqlalchemy import select
from task_manager.scheduler.db import TaskRun
from task_manager.tasks.helpers.custom_index_readiness import custom_index_pair_lock
from task_manager.scheduler.registry import task
from task_manager.scheduler.types import TaskStatus
from task_manager.scheduler.results import TaskResult

from .service import run_manage_custom_indexes, run_manage_profile_custom_indexes


def _dispatch_newer_generation_on_completion(
    *, resource_type: str, resource_id: int | None, task_run_id: int, **_,
) -> None:
    if resource_type != "show" or resource_id is None:
        return
    with db_session() as session:
        run = session.get(TaskRun, task_run_id)
        if run is None or run.status != TaskStatus.SUCCEEDED:
            return
        inputs = (run.meta or {}).get("inputs") or {}
        profile_id = inputs.get("local_media_profile_id")
        if not isinstance(profile_id, int):
            return
        state = session.scalar(select(CustomIndexState).where(
            CustomIndexState.show_id == resource_id,
            CustomIndexState.local_media_profile_id == profile_id,
        ))
        if state is not None and state.completed_generation != state.requested_generation:
            dispatch_custom_index_reconciliation(
                session, show_id=resource_id, local_media_profile_id=profile_id,
            )
            session.commit()


@task(
    key="manage_custom_indexes",
    title="Manage custom indexes",
    description="Derive Episode ranks for an applicable Show and Local Media Profile.",
    allowed_resource_types=("show", "local_media_profile"),
    default_max_retries=3,
    tracks_progress=True,
    terminal_callback=_dispatch_newer_generation_on_completion,
)
async def manage_custom_indexes(
    *,
    resource_id: int | None = None,
    progress=None,
    local_media_profile_id: int | None = None,
    rename_after: bool = False,
    profile_change_token: str | None = None,
) -> TaskResult:
    if resource_id is None:
        raise ValueError("Custom index management requires a resource")

    with db_session() as session:
        if local_media_profile_id is None:
            return await run_manage_profile_custom_indexes(
                session, local_media_profile_id=resource_id,
                rename_after=rename_after, progress=progress,
            )
        else:
            async with custom_index_pair_lock(resource_id, local_media_profile_id):
                return run_manage_custom_indexes(
                    session, show_id=resource_id,
                    local_media_profile_id=local_media_profile_id, progress=progress,
                )
