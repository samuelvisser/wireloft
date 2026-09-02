from typing import Optional, Sequence

from sqlalchemy.orm import Session
from sqlalchemy import select

from fastapi import HTTPException

from backend.api.helpers import update_database_fields
from backend.api.models.episode import *
from backend.db.models.media_item import Episode
from task_manager.events.transactional import queue_event


METADATA_REFRESH_REQUESTED_EVENT = "episode.metadata_refresh_requested"


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


def queue_episode_metadata_refresh(s: Session, episode: Episode) -> None:
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
) -> dict[str, bool | int]:
    episode = (
        s.query(Episode)
        .filter_by(slug=episode_slug)
        .one_or_none()
    )
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")

    queue_episode_metadata_refresh(s, episode)
    s.flush()
    return {"queued": True, "episode_id": episode.id}


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
