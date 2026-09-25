from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import CustomIndexState, Episode, Show, ShowLocalMediaProfile
from backend.db.models.media_download import EpisodeMediaDownload
from backend.services.custom_indexes import (
    profile_applies_to_show, reconcile_show_profile_custom_indexes,
)
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from task_manager.scheduler.operations import (
    OperationTargetSpec, create_operation, queue_operation_target_dispatch,
)
from task_manager.scheduler.results import TaskResult
from task_manager.scheduler.types import OperationSource
from task_manager.tasks.helpers.progress import update_progress
from task_manager.tasks.helpers.custom_index_readiness import custom_index_pair_lock


def _queue_targeted_rename(
    session: Session, *, show_id: int, local_media_profile_id: int,
    episode_ids: tuple[int, ...],
    expected_sources: tuple[tuple[int, str], ...],
) -> None:
    if not episode_ids:
        return
    target = OperationTargetSpec(
        task_key="rename_show_profile_files", resource_type="show",
        resource_id=show_id,
        task_kwargs={
            "local_media_profile_id": local_media_profile_id,
            "episode_ids": list(episode_ids),
            "expected_sources": {str(id_): path for id_, path in expected_sources},
        },
        slot_key=f"show:{show_id}:profile:{local_media_profile_id}",
    )
    operation = create_operation(
        session, kind="local_media_profile.rename_files",
        source=OperationSource.SYSTEM.value,
        resource_type="local_media_profile", resource_id=local_media_profile_id,
        title="Update synchronized file names after indexing",
        targets=[target],
    )
    queue_operation_target_dispatch(session, operation.id, target.resolved_slot_key())


def _queue_profile_rename(session: Session, profile: ShowLocalMediaProfile) -> bool:
    show_ids = tuple(sorted({
        show.id for show in session.scalars(select(Show)
            .join(Episode, Episode.show_id == Show.id)
            .join(EpisodeMediaDownload, EpisodeMediaDownload.media_item_id == Episode.id)
            .where(EpisodeMediaDownload.local_media_profile_id == profile.id,
                   EpisodeMediaDownload.artifact_status.in_((
                       MediaDownloadArtifactStatus.AVAILABLE.value,
                       MediaDownloadArtifactStatus.CORRUPTED.value,
                   ))))
        if profile_applies_to_show(profile, show)
    }))
    if not show_ids:
        return False
    targets = [
        OperationTargetSpec(
            task_key="rename_show_profile_files", resource_type="show",
            resource_id=show_id, task_kwargs={"local_media_profile_id": profile.id},
            slot_key=f"show:{show_id}",
        ) for show_id in show_ids
    ]
    operation = create_operation(
        session, kind="local_media_profile.rename_files",
        source=OperationSource.SYSTEM.value,
        resource_type="local_media_profile", resource_id=profile.id,
        title=profile.name, targets=targets,
    )
    for target in targets:
        queue_operation_target_dispatch(session, operation.id, target.resolved_slot_key())
    return True


def run_manage_custom_indexes(
    session: Session, *, show_id: int, local_media_profile_id: int, progress=None,
) -> TaskResult:
    update_progress(progress, 5, "Calculating Episode index ranks")
    while True:
        result = reconcile_show_profile_custom_indexes(
            session, show_id=show_id, local_media_profile_id=local_media_profile_id,
        )
        if not result.superseded:
            break
        session.rollback()
    _queue_targeted_rename(
        session, show_id=show_id, local_media_profile_id=local_media_profile_id,
        episode_ids=result.synced_episode_ids,
        expected_sources=result.synced_source_paths,
    )
    session.commit()
    update_progress(progress, 100, "Episode index ranks reconciled")
    return TaskResult(
        summary="Custom indexes reconciled",
        data={
            "episodes_considered": result.episodes_considered,
            "assignments_changed": result.assignments_changed,
            "files_to_rename": len(result.synced_episode_ids),
        },
    )


async def run_manage_profile_custom_indexes(
    session: Session, *, local_media_profile_id: int, rename_after: bool,
    progress=None,
) -> TaskResult:
    states = list(session.scalars(select(CustomIndexState).where(
        CustomIndexState.local_media_profile_id == local_media_profile_id,
    ).order_by(CustomIndexState.show_id)))
    changed = 0
    for index, state in enumerate(states, start=1):
        async with custom_index_pair_lock(state.show_id, local_media_profile_id):
            while True:
                result = reconcile_show_profile_custom_indexes(
                    session, show_id=state.show_id,
                    local_media_profile_id=local_media_profile_id,
                    auto_rename=False,
                )
                if not result.superseded:
                    break
                session.rollback()
            session.commit()
        changed += result.assignments_changed
        update_progress(progress, round(index / max(len(states), 1) * 90), f"Indexed {index}/{len(states)} shows")

    rename_queued = False
    if rename_after:
        profile = session.get(ShowLocalMediaProfile, local_media_profile_id)
        if profile is not None:
            rename_queued = _queue_profile_rename(session, profile)
            session.commit()
    update_progress(progress, 100, "Custom index maintenance complete")
    return TaskResult(
        summary="Custom index maintenance complete",
        data={"shows_considered": len(states), "assignments_changed": changed,
              "rename_queued": int(rename_queued)},
    )
