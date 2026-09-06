from typing import Optional, Sequence

from sqlalchemy.orm import Session
from sqlalchemy import select

from fastapi import HTTPException

from backend.api.helpers import update_database_fields
from backend.api.models.episode import *
from backend.db.models.media_item import Episode
from backend.types.episode_types import EpisodePublishStatus
from task_manager.events.transactional import queue_event
from task_manager.scheduler.operations import (
    OperationTargetSpec,
    create_operation,
    queue_operation_target_dispatch,
)


METADATA_REFRESH_REQUESTED_EVENT = "episode.metadata_refresh_requested"
_METADATA_REFRESH_TASK_KEY = "refresh_episode_metadata_worker"
_EARLY_DELETE_TASK_KEY = "cleanup_episodes_stuck_without_media"


def get_episodes_by_show_list(s: Session, show_slug: str, limit: int | None = None) -> list[EpisodeAPIRead]:
    stmt = (
        select(Episode)
        .filter(Episode.show.has(slug=show_slug))
        .order_by(Episode.published_date.desc())
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    episodes: Sequence[Episode] = s.scalars(stmt).all()

    return [EpisodeAPIRead.model_validate(mp) for mp in episodes]


def get_episode(s: Session, episode_slug: str) -> EpisodeAPIRead:
    episode = (
        s.query(Episode)
        .filter_by(slug=episode_slug)
        .one_or_none()
    )

    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")

    return EpisodeAPIRead.model_validate(episode)


def queue_episode_metadata_refresh(
        s: Session,
        episode: Episode,
) -> None:
    """Persist unfinished metadata state and queue the normal refresh worker."""
    episode.metadata_is_final = False
    queue_event(s, METADATA_REFRESH_REQUESTED_EVENT, {
        "resource_id": episode.id,
        "id": episode.id,
        "slug": episode.slug,
        "show_id": episode.show_id,
        "refresh": True,
    })


def request_episode_metadata_refresh(
        s: Session,
        episode_slug: str,
) -> dict[str, bool | int | str]:
    episode = (
        s.query(Episode)
        .filter_by(slug=episode_slug)
        .one_or_none()
    )
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")

    target = OperationTargetSpec(
        task_key=_METADATA_REFRESH_TASK_KEY,
        resource_type="episode",
        resource_id=episode.id,
        task_kwargs={"refresh": True},
    )
    show = episode.show
    operation = create_operation(
        s,
        kind="episode.refresh_metadata",
        resource_type="episode",
        resource_id=episode.id,
        title=episode.title,
        targets=[target],
        context={
            "episode_slug": episode.slug,
            "episode_title": episode.title,
            "show_id": episode.show_id,
            "show_slug": show.slug if show is not None else None,
            "show_title": show.title if show is not None else None,
        },
    )
    if queue_operation_target_dispatch(s, operation.id, target.resolved_slot_key()):
        episode.metadata_is_final = False
    s.flush()
    return {
        "queued": True,
        "episode_id": episode.id,
        "operation_id": operation.id,
    }


def request_episode_early_delete(
        s: Session,
        episode_slug: str,
) -> dict[str, bool | str]:
    """Queue the stuck-without-media cleanup worker as an explicit immediate delete."""
    episode = (
        s.query(Episode)
        .filter_by(slug=episode_slug)
        .one_or_none()
    )
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    if episode.publish_status != EpisodePublishStatus.DW_PROCESSING.value:
        raise HTTPException(
            status_code=409,
            detail="Early Delete is only available while an episode is processing on Daily Wire",
        )

    show = episode.show
    target = OperationTargetSpec(
        task_key=_EARLY_DELETE_TASK_KEY,
        resource_type="show",
        resource_id=episode.show_id,
        task_kwargs={
            "episode_id": episode.id,
            "force": True,
        },
        slot_key=f"{_EARLY_DELETE_TASK_KEY}:episode:{episode.id}:force",
    )
    operation = create_operation(
        s,
        kind="episode.early_delete",
        resource_type="episode",
        resource_id=episode.id,
        title=episode.title,
        targets=[target],
        context={
            "episode_slug": episode.slug,
            "episode_title": episode.title,
            "show_id": episode.show_id,
            "show_slug": show.slug if show is not None else None,
            "show_title": show.title if show is not None else None,
        },
    )
    queue_operation_target_dispatch(s, operation.id, target.resolved_slot_key())
    s.flush()
    return {
        "queued": True,
        "operation_id": operation.id,
    }


def create_episode(s: Session, body: EpisodeAPICreate) -> EpisodeAPIRead:
    # Build model from validated Pydantic data
    data = body.model_dump(by_alias=True)

    episode = Episode(**data)
    s.add(episode)
    s.flush()

    queue_event(s, "episode.added", {
        "resource_id": episode.id,
        "id": episode.id,
        "slug": episode.slug,
        "show_id": episode.show_id,
        "status": episode.publish_status
    })

    return EpisodeAPIRead.model_validate(episode)


def update_episode(s: Session, episode_slug: str, body: EpisodeAPIUpdate) -> EpisodeAPIRead:
    episode: Optional[Episode] = (
        s.query(Episode)
        .filter_by(slug=episode_slug)
        .one_or_none()
    )
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")

    old_status = episode.publish_status

    # Apply updates and flush; commit in router
    update_database_fields(episode, body)
    s.flush()

    # Emit status-specific events if status changed
    if hasattr(body, 'publish_status') and body.publish_status is not None and body.publish_status != old_status:
        event_data = {
            "old_status": old_status,
            "status": body.publish_status,
            "resource_id": episode.id,
            "id": episode.id,
            "slug": episode.slug,
            "show_id": episode.show_id,
        }
        queue_event(s, "episode.status_updated", event_data)

        if body.publish_status == EpisodePublishStatus.PUBLISHED_FINAL:
            queue_event(s, "episode.published_final", event_data)
        elif body.publish_status == EpisodePublishStatus.PUBLISHED_WITH_COUNTDOWN:
            queue_event(s, "episode.published_with_countdown", event_data)

    return EpisodeAPIRead.model_validate(episode)


def delete_episode(s: Session, episode_slug: str) -> EpisodeAPIRead:
    episode = (
        s.query(Episode)
        .filter_by(slug=episode_slug)
        .one_or_none()
    )
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")

    payload = EpisodeAPIRead.model_validate(episode)

    queue_event(s, "episode.deleted", {
        "resource_id": episode.id,
        "id": episode.id,
        "slug": episode.slug,
        "show_id": episode.show_id
    })

    s.delete(episode)
    s.flush()
    return payload
