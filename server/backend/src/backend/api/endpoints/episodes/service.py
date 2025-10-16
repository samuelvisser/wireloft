from typing import Sequence

from sqlalchemy.orm import Session
from sqlalchemy import select

from fastapi import HTTPException

from backend.api.helpers import update_database_fields
from backend.api.models.episode import *
from backend.db.models.media_item import Episode


def get_episodes_by_show_list(s: Session, show_slug: str) -> list[EpisodeAPIRead]:
    episodes: Sequence[Episode] = s.scalars(
        select(Episode)
        .filter(Episode.show.has(slug=show_slug))
        .order_by(Episode.index.desc())
    ).all()

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
    return EpisodeAPIRead.model_validate(episode)


def update_episode(s: Session, episode_slug: str, body: EpisodeAPIUpdate) -> EpisodeAPIRead:
    episode: Optional[Episode] = (
        s.query(Episode)
        .filter_by(slug=episode_slug)
        .one_or_none()
    )
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")

    # Apply updates and flush; commit in router
    update_database_fields(episode, body)
    s.flush()
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
    s.delete(episode)
    s.flush()
    return payload