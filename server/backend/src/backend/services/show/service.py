from flask import jsonify

from backend.app import db_session
from backend.db.models import Show
from .response_models import ShowItem, ErrorResponse


def get_show_list():
    with db_session() as s:
        shows = (
            s.query(Show)
            .order_by(Show.id)
            .all()
        )
        payload = [
            ShowItem(
                id=sh.slug,  # keep legacy behavior using slug as id in the list
                title=sh.title,
                author=sh.author_name,
                years="unknown",
            ).model_dump()
            for sh in shows
        ]
        return jsonify(payload)


def get_show(show_id: str):
    with db_session() as s:
        show = s.query(Show).filter_by(slug=show_id).one_or_none()
        if show is None:
            return jsonify(ErrorResponse(error="Show not found").model_dump()), 404
        desc = show.description
        prefix = "Years: "
        years = desc[len(prefix):] if (isinstance(desc, str) and desc.startswith(prefix)) else desc
        payload = ShowItem(
            id=show.slug,
            title=show.title,
            author=show.author_name,
            years=years,
        ).model_dump()
        return jsonify(payload)
