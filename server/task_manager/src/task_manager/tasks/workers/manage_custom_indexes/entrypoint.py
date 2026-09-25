from __future__ import annotations

from sqlalchemy import select

from backend.db.models import ShowLocalMediaProfile
from backend.services.custom_indexes import (
    CUSTOM_INDEXES_REQUESTED_EVENT,
    profile_uses_custom_indexes,
)
from controller.db_utils import db_session
from task_manager.scheduler.registry import on_event, task
from task_manager.scheduler.results import TaskResult

from .service import run_manage_custom_indexes


@on_event(CUSTOM_INDEXES_REQUESTED_EVENT, resource_type="show")
@task(
    key="manage_custom_indexes",
    title="Manage custom indexes",
    description="Allocate missing persistent custom index values for existing downloads.",
    allowed_resource_types=("show",),
    default_max_retries=3,
    tracks_progress=True,
)
async def manage_custom_indexes(
    *,
    resource_id: int | None = None,
    progress=None,
    local_media_profile_id: int | None = None,
    rename_after: bool = False,
) -> TaskResult:
    if resource_id is None:
        raise ValueError("Custom index management requires a show resource")

    with db_session() as session:
        if local_media_profile_id is not None:
            return run_manage_custom_indexes(
                session,
                show_id=resource_id,
                local_media_profile_id=local_media_profile_id,
                rename_after=rename_after,
                progress=progress,
            )

        profiles = [
            profile
            for profile in session.scalars(
                select(ShowLocalMediaProfile).order_by(ShowLocalMediaProfile.id.asc())
            )
            if profile_uses_custom_indexes(profile)
        ]
        if not profiles:
            return TaskResult(
                summary="No custom-index Local Media Profiles to reconcile",
                data={"profiles_updated": 0, "assignments_created": 0},
            )

        created = 0
        for index, profile in enumerate(profiles, start=1):
            result = run_manage_custom_indexes(
                session,
                show_id=resource_id,
                local_media_profile_id=profile.id,
                progress=None,
            )
            data = result.data if isinstance(result.data, dict) else {}
            created += int(data.get("assignments_created", 0) or 0)
            if progress is not None:
                progress.set(
                    round(index / len(profiles) * 100),
                    f"Checked custom indexes for {index}/{len(profiles)} Local Media Profiles",
                )

        return TaskResult(
            summary="Custom index assignments updated for show",
            data={
                "profiles_updated": len(profiles),
                "assignments_created": created,
            },
        )
