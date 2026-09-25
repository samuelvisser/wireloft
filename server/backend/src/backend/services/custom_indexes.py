from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.models import CustomIndexState, Episode, Metadata, Show, ShowLocalMediaProfile
from backend.db.models.media_download import EpisodeMediaDownload, MediaDownloadBase
from backend.utils.custom_index import (
    INDEX_ASSIGNMENT_PREFIX,
    get_media_download_index_assignments,
    index_assignment_storage_key,
    indexing_value_definition_keys,
    set_media_download_index_assignment,
)
from backend.utils.output_template import (
    SHOW_OUTPUT_TEMPLATE_FIELDS,
    SHOW_OUTPUT_TEMPLATE_METADATA_SCOPES,
    episode_output_template_values,
    output_template_custom_index_keys,
    render_output_template,
)


CUSTOM_INDEXES_REQUESTED_EVENT = "show.custom_indexes_requested"


@dataclass(frozen=True)
class CustomIndexReconciliationResult:
    show_id: int
    local_media_profile_id: int
    downloads_considered: int
    assignments_created: int
    changed_media_download_ids: tuple[int, ...]


def profile_uses_custom_indexes(profile: ShowLocalMediaProfile) -> bool:
    return bool(output_template_custom_index_keys(profile.output_template))


def _counter_query(
    *,
    show_id: int,
    local_media_profile_id: int,
    key: str,
):
    return select(CustomIndexState).where(
        CustomIndexState.show_id == show_id,
        CustomIndexState.local_media_profile_id == local_media_profile_id,
        CustomIndexState.key == key,
    )


def _increment_existing_counter(
    session: Session,
    *,
    show_id: int,
    local_media_profile_id: int,
    key: str,
) -> int | None:
    next_value = session.scalar(
        update(CustomIndexState)
        .where(
            CustomIndexState.show_id == show_id,
            CustomIndexState.local_media_profile_id == local_media_profile_id,
            CustomIndexState.key == key,
        )
        .values(next_value=CustomIndexState.next_value + 1)
        .returning(CustomIndexState.next_value)
    )
    return int(next_value) - 1 if next_value is not None else None


def allocate_custom_index(
    session: Session,
    *,
    show_id: int,
    local_media_profile_id: int,
    key: str,
) -> int:
    """Atomically allocate the next persistent value for one logical sequence."""
    value = _increment_existing_counter(
        session,
        show_id=show_id,
        local_media_profile_id=local_media_profile_id,
        key=key,
    )
    if value is not None:
        return value

    # The first allocator creates the unique state row and consumes value 1.
    # A concurrent first allocator loses the unique insert race, then performs
    # the same atomic increment used for every later value.
    try:
        with session.begin_nested():
            session.add(CustomIndexState(
                show_id=show_id,
                local_media_profile_id=local_media_profile_id,
                key=key,
                next_value=2,
            ))
            session.flush()
        return 1
    except IntegrityError:
        value = _increment_existing_counter(
            session,
            show_id=show_id,
            local_media_profile_id=local_media_profile_id,
            key=key,
        )
        if value is None:
            raise RuntimeError(
                "Custom index allocation state disappeared after a concurrent insert"
            )
        return value


def peek_next_custom_index(
    session: Session,
    *,
    show_id: int,
    local_media_profile_id: int,
    key: str,
) -> int:
    state = session.scalar(
        _counter_query(
            show_id=show_id,
            local_media_profile_id=local_media_profile_id,
            key=key,
        )
    )
    return state.next_value if state is not None else 1


def ensure_media_download_custom_indexes(
    session: Session,
    *,
    download: EpisodeMediaDownload,
    profile: ShowLocalMediaProfile,
    episode: Episode,
) -> dict[str, int]:
    """Allocate only the custom indexes actually reached by this download's Jinja."""
    template_keys = output_template_custom_index_keys(profile.output_template)
    assignments = get_media_download_index_assignments(download)
    if not template_keys:
        return assignments

    definitions = indexing_value_definition_keys(episode.show)

    def resolve_index(key: str) -> object:
        if key not in definitions:
            return ""
        value = assignments.get(key)
        if value is None:
            value = allocate_custom_index(
                session,
                show_id=episode.show_id,
                local_media_profile_id=profile.id,
                key=key,
            )
            set_media_download_index_assignment(download, key, value)
            assignments[key] = value
        return value

    # Rendering is deliberate: only keys reached by the active Jinja branch are
    # allocated. Static references in dead branches never create assignments.
    render_output_template(
        profile.output_template,
        episode_output_template_values(episode),
        allowed_fields=SHOW_OUTPUT_TEMPLATE_FIELDS,
        allowed_metadata_scopes=SHOW_OUTPUT_TEMPLATE_METADATA_SCOPES,
        custom_index_resolver=resolve_index,
    )
    session.flush()
    return assignments


def reconcile_show_profile_custom_indexes(
    session: Session,
    *,
    show_id: int,
    local_media_profile_id: int,
) -> CustomIndexReconciliationResult:
    show = session.get(Show, show_id)
    profile = session.get(ShowLocalMediaProfile, local_media_profile_id)
    if show is None or profile is None:
        return CustomIndexReconciliationResult(
            show_id=show_id,
            local_media_profile_id=local_media_profile_id,
            downloads_considered=0,
            assignments_created=0,
            changed_media_download_ids=(),
        )

    downloads = list(session.scalars(
        select(EpisodeMediaDownload)
        .join(Episode, Episode.id == EpisodeMediaDownload.media_item_id)
        .where(
            Episode.show_id == show_id,
            EpisodeMediaDownload.local_media_profile_id == local_media_profile_id,
        )
        .order_by(Episode.index.asc(), EpisodeMediaDownload.id.asc())
    ))

    changed: list[int] = []
    created = 0
    for download in downloads:
        episode = session.get(Episode, download.media_item_id)
        if episode is None:
            continue
        before = get_media_download_index_assignments(download)
        after = ensure_media_download_custom_indexes(
            session,
            download=download,
            profile=profile,
            episode=episode,
        )
        added = set(after) - set(before)
        if added:
            changed.append(download.id)
            created += len(added)

    return CustomIndexReconciliationResult(
        show_id=show.id,
        local_media_profile_id=profile.id,
        downloads_considered=len(downloads),
        assignments_created=created,
        changed_media_download_ids=tuple(changed),
    )


def remove_show_indexing_value_assignments(
    session: Session,
    *,
    show_id: int,
    keys: set[str] | frozenset[str],
) -> None:
    if not keys:
        return

    download_ids = (
        select(EpisodeMediaDownload.id)
        .join(Episode, Episode.id == EpisodeMediaDownload.media_item_id)
        .where(Episode.show_id == show_id)
    )
    storage_keys = [index_assignment_storage_key(key) for key in keys]
    session.execute(
        delete(Metadata).where(
            Metadata.parent_table == MediaDownloadBase.__tablename__,
            Metadata.parent_id.in_(download_ids),
            Metadata.key.in_(storage_keys),
        )
    )
    session.execute(
        delete(CustomIndexState).where(
            CustomIndexState.show_id == show_id,
            CustomIndexState.key.in_(keys),
        )
    )
    session.flush()


def remove_profile_custom_index_state(
    session: Session,
    *,
    local_media_profile_id: int,
) -> None:
    download_ids = select(MediaDownloadBase.id).where(
        MediaDownloadBase.local_media_profile_id == local_media_profile_id,
    )
    escaped_prefix = (
        INDEX_ASSIGNMENT_PREFIX
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    session.execute(
        delete(Metadata).where(
            Metadata.parent_table == MediaDownloadBase.__tablename__,
            Metadata.parent_id.in_(download_ids),
            Metadata.key.like(f"{escaped_prefix}%", escape="\\"),
        )
    )
    session.execute(
        delete(CustomIndexState).where(
            CustomIndexState.local_media_profile_id == local_media_profile_id,
        )
    )
    session.flush()
