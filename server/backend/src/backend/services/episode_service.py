from flask import jsonify
from sqlalchemy import cast, Integer

from backend.app import db_session
from backend.db.models import Show, Episode


def get_episode_list(show_id: str):
    with db_session() as s:
        show = s.query(Show).filter_by(slug=show_id).one_or_none()
        if show is None:
            return jsonify({"error": "Show not found"}), 404
        episodes = (
            s.query(Episode)
            .filter_by(show_id=str(show.id))
            .order_by(cast(Episode.id, Integer))
            .all()
        )
        payload = [
            {
                "id": (ep.slug or str(ep.id)),
                "title": ep.title,
                "index": (int(ep.id) if isinstance(ep.id, str) and ep.id.isdigit() else None),
                "status": (ep.status or "downloaded"),
            }
            for ep in episodes
        ]
        return jsonify(payload)


def get_episode(show_id: str, episode_slug: str):
    with db_session() as s:
        show = s.query(Show).filter_by(slug=show_id).one_or_none()
        if show is None:
            return jsonify({"error": "Show not found"}), 404
        ep = (
            s.query(Episode)
            .filter_by(show_id=str(show.id), slug=episode_slug)
            .one_or_none()
        )
        if ep is None:
            return jsonify({"error": "Episode not found"}), 404
        payload = {
            "id": (ep.slug or str(ep.id)),
            "title": ep.title,
            "index": (int(ep.id) if isinstance(ep.id, str) and ep.id.isdigit() else None),
            "status": (ep.status or "downloaded"),
        }
        return jsonify(payload)