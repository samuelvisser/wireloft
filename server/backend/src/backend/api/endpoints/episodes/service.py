from typing import Sequence

from sqlalchemy.orm import Session
from sqlalchemy import select

from fastapi import HTTPException

from backend.api.helpers import update_database_fields
from backend.api.models.episode import *
from backend.db.models.media_item import Episode
from task_manager.events.emitters import emit_event


def get_episodes_by_show_list(s: Session, show_slug: str, limit: int | None = None) -> list[EpisodeAPIRead]:
    stmt = (
        select(Episode)
        .filter(Episode.show.has(slug=show_slug))
        .order_by(Episode.index.desc())
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


def create_episode(s: Session, body: EpisodeAPICreate) -> EpisodeAPIRead:
    # Build model from validated Pydantic data
    data = body.model_dump(by_alias=True)

    episode = Episode(**data)
    s.add(episode)
    s.flush()

    emit_event("episode.added", {
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
        emit_event("episode.status_updated", {
            "old_status": old_status,
            "status": body.publish_status,
            "resource_id": episode.id,
            "id": episode.id,
            "show_id": episode.show_id
        })

        if body.publish_status == EpisodePublishStatus.PUBLISHED_FINAL:
            emit_event("episode.published_final", {
                "resource_id": episode.id,
                "id": episode.id,
                "show_id": episode.show_id
            })
        elif body.publish_status == EpisodePublishStatus.PUBLISHED_WITH_COUNTDOWN:
            emit_event("episode.published_with_countdown", {
                "resource_id": episode.id,
                "id": episode.id,
                "show_id": episode.show_id
            })

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

    emit_event("episode.deleted", {
        "resource_id": episode.id,
        "id": episode.id,
        "show_id": episode.show_id
    })

    s.delete(episode)
    s.flush()
    return payload