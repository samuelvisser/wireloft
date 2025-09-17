from __future__ import annotations

from fastapi import HTTPException

from backend.api.models.show import ShowAPIReadView
from backend.app import db_session
from backend.db.models import Show


def get_show_views_list() -> list[ShowAPIReadView]:
    with db_session() as s:
        shows = (
            s.query(Show)
            .order_by(Show.title.asc())
            .all()
        )
        return [ShowAPIReadView.model_validate(show) for show in shows]


def get_show_view(show_slug: str) -> ShowAPIReadView:
    with db_session() as s:
        show = (
            s.query(Show)
            .filter_by(slug=show_slug)
            .one_or_none()
        )

        if show is None:
            raise HTTPException(status_code=404, detail="Show not found")

        return ShowAPIReadView.model_validate(show)