from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from backend.db.models import CustomIndexState, Episode, Metadata, Show, ShowLocalMediaProfile
from backend.db.models.media_download import EpisodeMediaDownload
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from backend.types.local_media_profile_types import ShowLocalMediaProfileScope
from backend.utils.custom_index import (
    CustomIndexNotReadyError,
    INDEX_ASSIGNMENT_PREFIX,
    get_episode_index_assignments,
    indexing_value_definition_keys,
    set_episode_index_assignment,
)
from backend.utils.output_template import (
    SHOW_OUTPUT_TEMPLATE_FIELDS,
    SHOW_OUTPUT_TEMPLATE_METADATA_SCOPES,
    episode_output_template_values,
    output_template_custom_index_keys,
    render_output_template,
    resolve_episode_output_path_with_index_values,
)
from task_manager.scheduler.operations import (
    OperationTargetSpec, create_operation, queue_operation_target_dispatch,
)
from task_manager.scheduler.types import OperationSource
from task_manager.scheduler.types import OperationStatus
from task_manager.scheduler.db import TaskOperation, TaskOperationTarget


@dataclass(frozen=True)
class CustomIndexReconciliationResult:
    show_id: int
    local_media_profile_id: int
    episodes_considered: int
    assignments_changed: int
    synced_episode_ids: tuple[int, ...]
    superseded: bool = False
    synced_source_paths: tuple[tuple[int, str], ...] = ()


def profile_applies_to_show(profile: ShowLocalMediaProfile, show: Show) -> bool:
    return profile.show_scope == ShowLocalMediaProfileScope.BOTH.value or profile.show_scope == show.type


def profile_uses_custom_indexes(profile: ShowLocalMediaProfile) -> bool:
    return bool(
        output_template_custom_index_keys(profile.output_template)
        & indexing_value_definition_keys(profile)
    )


def request_custom_index_reconciliation(
    session: Session, *, show_id: int, local_media_profile_id: int,
    dispatch: bool = True,
) -> CustomIndexState:
    """Invalidate a pair in the transaction that changes its inputs."""
    state = session.scalar(select(CustomIndexState).where(
        CustomIndexState.show_id == show_id,
        CustomIndexState.local_media_profile_id == local_media_profile_id,
    ))
    if state is None:
        state = CustomIndexState(show_id=show_id, local_media_profile_id=local_media_profile_id)
        session.add(state)
        session.flush()
    else:
        session.execute(update(CustomIndexState).where(CustomIndexState.id == state.id).values(
            requested_generation=CustomIndexState.requested_generation + 1,
        ))
        session.refresh(state)
    if dispatch:
        dispatch_custom_index_reconciliation(
            session, show_id=show_id, local_media_profile_id=local_media_profile_id,
        )
    return state


def dispatch_custom_index_reconciliation(
    session: Session, *, show_id: int, local_media_profile_id: int,
) -> None:
    active = session.scalar(select(TaskOperationTarget.id).join(
        TaskOperation, TaskOperation.id == TaskOperationTarget.operation_id,
    ).where(
        TaskOperation.kind == "local_media_profile.manage_custom_indexes",
        TaskOperation.resource_id == local_media_profile_id,
        TaskOperationTarget.resource_type == "show",
        TaskOperationTarget.resource_id == show_id,
        TaskOperation.status.in_((
            OperationStatus.QUEUED.value, OperationStatus.RUNNING.value,
            OperationStatus.WAITING.value,
        )),
    ).limit(1))
    if active is not None:
        return
    target = OperationTargetSpec(
            task_key="manage_custom_indexes", resource_type="show", resource_id=show_id,
            task_kwargs={"local_media_profile_id": local_media_profile_id},
            slot_key=f"show:{show_id}:profile:{local_media_profile_id}",
    )
    operation = create_operation(
            session, kind="local_media_profile.manage_custom_indexes",
            source=OperationSource.SYSTEM.value,
            resource_type="local_media_profile", resource_id=local_media_profile_id,
            title="Manage custom indexes", targets=[target],
    )
    queue_operation_target_dispatch(session, operation.id, target.resolved_slot_key())


def request_show_custom_index_reconciliation(session: Session, show_id: int) -> None:
    show = session.get(Show, show_id)
    if show is None:
        return
    for profile in session.scalars(select(ShowLocalMediaProfile).order_by(ShowLocalMediaProfile.id)):
        previous = session.scalar(select(CustomIndexState.id).where(
            CustomIndexState.show_id == show_id,
            CustomIndexState.local_media_profile_id == profile.id,
        ))
        if previous is not None or (profile_applies_to_show(profile, show) and profile_uses_custom_indexes(profile)):
            request_custom_index_reconciliation(
                session, show_id=show_id, local_media_profile_id=profile.id,
            )


def ensure_episode_custom_indexes_ready(
    session: Session, *, episode: Episode, profile: ShowLocalMediaProfile,
) -> None:
    if not profile_uses_custom_indexes(profile):
        return
    state = session.scalar(select(CustomIndexState).where(
        CustomIndexState.show_id == episode.show_id,
        CustomIndexState.local_media_profile_id == profile.id,
    ))
    if state is None:
        raise CustomIndexNotReadyError(
            "Custom indexes have not been reconciled",
            repair_show_id=episode.show_id, repair_profile_id=profile.id,
        )
    if state.completed_generation != state.requested_generation:
        raise CustomIndexNotReadyError("Waiting for Manage Custom Indexes to complete")


def simulate_episode_indexes(
    episodes: list[Episode], *, template: str, definitions: frozenset[str],
    values_overrides: dict[int, dict[str, str]] | None = None,
) -> dict[int, dict[str, int]]:
    """Evaluate Jinja branches in canonical order without persisting anything."""
    counters: dict[str, int] = defaultdict(int)
    desired: dict[int, dict[str, int]] = {}
    for episode in sorted(episodes, key=lambda item: (item.index, item.id)):
        selected: dict[str, int] = {}

        def resolve(key: str) -> object:
            if key not in definitions:
                return ""
            if key not in selected:
                counters[key] += 1
                selected[key] = counters[key]
            return selected[key]

        render_output_template(
            template, (values_overrides or {}).get(episode.id) or episode_output_template_values(episode),
            allowed_fields=SHOW_OUTPUT_TEMPLATE_FIELDS,
            allowed_metadata_scopes=SHOW_OUTPUT_TEMPLATE_METADATA_SCOPES,
            custom_index_resolver=resolve,
        )
        desired[episode.id] = selected
    return desired


def _synced_downloads_before_reindex(
    session: Session, profile: ShowLocalMediaProfile, episodes: list[Episode],
) -> dict[int, str]:
    """Only previously synchronized physical paths qualify for an automatic move."""
    episode_by_id = {episode.id: episode for episode in episodes}
    if not episode_by_id:
        return {}
    downloads = session.scalars(select(EpisodeMediaDownload).where(
        EpisodeMediaDownload.media_item_id.in_(episode_by_id),
        EpisodeMediaDownload.local_media_profile_id == profile.id,
        EpisodeMediaDownload.artifact_status.in_((
            MediaDownloadArtifactStatus.AVAILABLE.value,
            MediaDownloadArtifactStatus.CORRUPTED.value,
        )),
    ))
    synced: dict[int, str] = {}
    definitions = indexing_value_definition_keys(profile)
    for download in downloads:
        episode = episode_by_id[download.media_item_id]
        source = Path(download.file_path)
        if not source.suffix or not source.is_file():
            continue
        try:
            old_path = resolve_episode_output_path_with_index_values(
                profile.output_template, episode=episode, index_definitions=definitions,
                index_values=get_episode_index_assignments(episode, profile.id),
                extension=source.suffix.removeprefix("."),
            )
        except (CustomIndexNotReadyError, ValueError):
            continue
        if source == old_path:
            synced[episode.id] = str(source)
    return synced


def reconcile_show_profile_custom_indexes(
    session: Session, *, show_id: int, local_media_profile_id: int,
    auto_rename: bool = True,
) -> CustomIndexReconciliationResult:
    state = session.scalar(select(CustomIndexState).where(
        CustomIndexState.show_id == show_id,
        CustomIndexState.local_media_profile_id == local_media_profile_id,
    ))
    profile = session.get(ShowLocalMediaProfile, local_media_profile_id)
    show = session.get(Show, show_id)
    empty = CustomIndexReconciliationResult(show_id, local_media_profile_id, 0, 0, ())
    if state is None or profile is None or show is None:
        return empty

    generation = state.requested_generation
    episodes = list(session.scalars(select(Episode).where(Episode.show_id == show_id)
        .order_by(Episode.index.asc(), Episode.id.asc())))
    applicable = profile_applies_to_show(profile, show)
    desired = simulate_episode_indexes(
        episodes, template=profile.output_template,
        definitions=indexing_value_definition_keys(profile),
    ) if applicable and profile_uses_custom_indexes(profile) else {ep.id: {} for ep in episodes}
    old = {ep.id: get_episode_index_assignments(ep, profile.id) for ep in episodes}
    synced = _synced_downloads_before_reindex(session, profile, episodes) if auto_rename and applicable else {}

    # Compare-and-swap and metadata edits belong to the same transaction.
    updated = session.execute(update(CustomIndexState).where(
        CustomIndexState.id == state.id,
        CustomIndexState.requested_generation == generation,
    ).values(completed_generation=generation)).rowcount
    if not updated:
        return CustomIndexReconciliationResult(show_id, local_media_profile_id, len(episodes), 0, (), True)

    changed = 0
    synced_episode_ids: list[int] = []
    for episode in episodes:
        before, after = old[episode.id], desired[episode.id]
        raw_count = sum(
            item.key.startswith(f"{INDEX_ASSIGNMENT_PREFIX}{profile.id}.")
            for item in episode.meta_items
        )
        if before == after and raw_count == len(after):
            continue
        changed += max(1, len(set(before.items()) ^ set(after.items())))
        prefix = f"{INDEX_ASSIGNMENT_PREFIX}{profile.id}."
        seen: set[str] = set()
        for item in list(episode.meta_items):
            if not item.key.startswith(prefix):
                continue
            key = item.key[len(prefix):]
            if key not in after or key in seen:
                episode.meta_items.remove(item)
                continue
            seen.add(key)
            if item.value != str(after[key]):
                item.value = str(after[key])
        for key, value in after.items():
            if key not in seen:
                set_episode_index_assignment(episode, profile.id, key, value)
        if episode.id in synced:
            synced_episode_ids.append(episode.id)
    session.flush()
    return CustomIndexReconciliationResult(
        show_id, local_media_profile_id, len(episodes), changed, tuple(synced_episode_ids),
        synced_source_paths=tuple((id_, synced[id_]) for id_ in synced_episode_ids),
    )


def remove_profile_custom_index_state(session: Session, *, local_media_profile_id: int) -> None:
    prefix = f"{INDEX_ASSIGNMENT_PREFIX}{local_media_profile_id}."
    escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    session.execute(delete(Metadata).where(
        Metadata.parent_table == Episode.__tablename__,
        Metadata.key.like(f"{escaped}%", escape="\\"),
    ))
    session.execute(delete(CustomIndexState).where(
        CustomIndexState.local_media_profile_id == local_media_profile_id,
    ))
    session.flush()
