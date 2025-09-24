from __future__ import annotations

from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.api.models.show import ShowAPIReadView
from backend.db.models import Show


def get_show_views_list(s: Session) -> list[ShowAPIReadView]:
    shows = (
        s.query(Show)
        .order_by(Show.title.asc())
        .all()
    )
    return [ShowAPIReadView.model_validate(show) for show in shows]


def get_show_view(s: Session, show_slug: str) -> ShowAPIReadView:
    show = (
        s.query(Show)
        .filter_by(slug=show_slug)
        .one_or_none()
    )

    if show is None:
        raise HTTPException(status_code=404, detail="Show not found")

    return ShowAPIReadView.model_validate(show)