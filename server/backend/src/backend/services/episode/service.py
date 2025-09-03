from fastapi import HTTPException
from sqlalchemy import cast, Integer

from backend.app import db_session
from backend.db.models import Show, Episode
from .response_models import EpisodeItem


def get_episode_list(show_id: str) -> list[EpisodeItem]:
    with db_session() as s:
        show = s.query(Show).filter_by(slug=show_id).one_or_none()
        if show is None:
            raise HTTPException(status_code=404, detail="Show not found")
        episodes = (
            s.query(Episode)
            .filter_by(show_id=str(show.id))
            .order_by(cast(Episode.id, Integer))
            .all()
        )
        payload = [
            EpisodeItem(
                id=(ep.slug or str(ep.id)),
                title=ep.title,
                index=(int(ep.id) if isinstance(ep.id, str) and ep.id.isdigit() else None),
                status=(ep.status or "downloaded"),
            )
            for ep in episodes
        ]
        return payload


def get_episode(show_id: str, episode_slug: str) -> EpisodeItem:
    with db_session() as s:
        show = s.query(Show).filter_by(slug=show_id).one_or_none()
        if show is None:
            raise HTTPException(status_code=404, detail="Show not found")
        ep = (
            s.query(Episode)
            .filter_by(show_id=str(show.id), slug=episode_slug)
            .one_or_none()
        )
        if ep is None:
            raise HTTPException(status_code=404, detail="Episode not found")
        payload = EpisodeItem(
            id=(ep.slug or str(ep.id)),
            title=ep.title,
            index=(int(ep.id) if isinstance(ep.id, str) and ep.id.isdigit() else None),
            status=(ep.status or "downloaded"),
        )
        return payload
