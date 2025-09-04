from fastapi import HTTPException

from backend.app import db_session
from backend.db.models import Show, Episode
from .response_models import EpisodeItemResponse

def _get_show_by_slug(slug: str) -> Show:
    with db_session() as s:
        show = s.query(Show).filter_by(slug=slug).one_or_none()
        if show is None:
            raise HTTPException(status_code=404, detail="Show not found")
        return show

def get_episode_list(show_slug: str) -> list[EpisodeItemResponse]:
    with db_session() as s:
        show = _get_show_by_slug(show_slug)
        episodes = (
            s.query(Episode)
            .filter_by(show_id=show.id)
            .order_by(Episode.index)
            .all()
        )
        payload = [
            EpisodeItemResponse.model_validate(ep, from_attributes=True)
            for ep in episodes
        ]
        return payload


def get_episode(show_slug: str, episode_slug: str) -> EpisodeItemResponse:
    with db_session() as s:
        show = _get_show_by_slug(show_slug)
        ep = (
            s.query(Episode)
            .filter_by(show_id=show.id, slug=episode_slug)
            .one_or_none()
        )
        if ep is None:
            raise HTTPException(status_code=404, detail="Episode not found")

        payload = EpisodeItemResponse.model_validate(ep, from_attributes=True)
        return payload
