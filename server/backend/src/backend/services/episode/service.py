from flask import jsonify
from sqlalchemy import cast, Integer

from backend.app import db_session
from backend.db.models import Show, Episode
from .response_models import EpisodeItem
from backend.services.common.response_models import ErrorResponse


def get_episode_list(show_id: str):
    with db_session() as s:
        show = s.query(Show).filter_by(slug=show_id).one_or_none()
        if show is None:
            return jsonify(ErrorResponse(error="Show not found").model_dump()), 404
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
            ).model_dump()
            for ep in episodes
        ]
        return jsonify(payload)


def get_episode(show_id: str, episode_slug: str):
    with db_session() as s:
        show = s.query(Show).filter_by(slug=show_id).one_or_none()
        if show is None:
            return jsonify(ErrorResponse(error="Show not found").model_dump()), 404
        ep = (
            s.query(Episode)
            .filter_by(show_id=str(show.id), slug=episode_slug)
            .one_or_none()
        )
        if ep is None:
            return jsonify(ErrorResponse(error="Episode not found").model_dump()), 404
        payload = EpisodeItem(
            id=(ep.slug or str(ep.id)),
            title=ep.title,
            index=(int(ep.id) if isinstance(ep.id, str) and ep.id.isdigit() else None),
            status=(ep.status or "downloaded"),
        ).model_dump()
        return jsonify(payload)
