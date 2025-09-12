from fastapi import HTTPException

from backend.api.helpers import update_database_fields
from backend.api.models.episode import *
from backend.app import db_session
from backend.db.models import Episode


def get_episodes_list(show_slug: str) -> list[EpisodeAPIRead]:
    with db_session() as s:
        episodes = (
            s.query(Episode)
            .filter(
                Episode.show.has(slug=show_slug)
            )
            .order_by(Episode.index.desc())
            .all()
        )

        return [EpisodeAPIRead.model_validate(mp, from_attributes=True) for mp in episodes]


def get_episode(show_slug: str, episode_slug: str) -> EpisodeAPIRead:
    with db_session() as s:
        episode = (
            s.query(Episode)
            .filter(
                Episode.slug == episode_slug,
                Episode.show.has(slug=show_slug)
            )
            .one_or_none()
        )

        if episode is None:
            raise HTTPException(status_code=404, detail="Episode not found")

        return EpisodeAPIRead.model_validate(episode, from_attributes=True)


def create_episode(body: EpisodeAPICreate) -> EpisodeAPIRead:
    with db_session() as s:
        # Build model from validated Pydantic data
        data = body.model_dump(by_alias=True)

        ep = Episode(**data)
        s.add(ep)
        s.commit()
        s.refresh(ep)
        return EpisodeAPIRead.model_validate(ep, from_attributes=True)


def update_episode(show_slug: str, episode_slug: str, body: EpisodeAPIUpdate) -> EpisodeAPIRead:
    with db_session() as s:
        episode = (
            s.query(Episode)
            .filter(
                Episode.slug == episode_slug,
                Episode.show.has(slug=show_slug)
            )
            .one_or_none()
        )
        if episode is None:
            raise HTTPException(status_code=404, detail="Episode not found")

        # Commit and return
        update_database_fields(episode, body)
        s.commit()
        s.refresh(episode)
        return EpisodeAPIRead.model_validate(episode, from_attributes=True)


def delete_episode(show_slug: str, episode_slug: str) -> EpisodeAPIRead:
    with db_session() as s:
        episode = (
            s.query(Episode)
            .filter(
                Episode.slug == episode_slug,
                Episode.show.has(slug=show_slug)
            )
            .one_or_none()
        )
        if episode is None:
            raise HTTPException(status_code=404, detail="Episode not found")

        payload = EpisodeAPIRead.model_validate(episode, from_attributes=True)
        s.delete(episode)
        s.commit()
        return payload