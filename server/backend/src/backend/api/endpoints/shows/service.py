from __future__ import annotations

from sqlalchemy.orm import Session
from backend.api.helpers import update_database_fields
from backend.api.models.show import *

from fastapi import HTTPException

from backend.db.models import Show
from wireloft_motherboard import events


def get_shows_list(s: Session) -> list[ShowAPIRead]:
    shows = (
        s.query(Show)
        .order_by(Show.title.asc())
        .all()
    )
    return [ShowAPIRead.model_validate(show) for show in shows]


def get_show(s: Session, show_slug: str) -> ShowAPIRead:
    show = (
        s.query(Show)
        .filter_by(slug=show_slug)
        .one_or_none()
    )

    if show is None:
        raise HTTPException(status_code=404, detail="Show not found")

    return ShowAPIRead.model_validate(show)


def create_show(s: Session, body: ShowAPICreate) -> ShowAPIRead:
    # Build model from validated Pydantic data
    data = body.model_dump(by_alias=True)

    show = Show(**data)
    s.add(show)
    s.flush()

    event_emitter = events.get_wireloft_event_emitter()
    event_emitter.emit("show_created", show.id)

    return ShowAPIRead.model_validate(show)


def update_show(s: Session, show_slug: str, body: ShowAPIUpdate) -> ShowAPIRead:
    show: Optional[Show] = (
        s.query(Show)
        .filter_by(slug=show_slug)
        .one_or_none()
    )
    if show is None:
        raise HTTPException(status_code=404, detail="Show not found")

    # Apply changes and flush
    update_database_fields(show, body)
    s.flush()

    event_emitter = events.get_wireloft_event_emitter()
    event_emitter.emit("show_updated", show.id)

    return ShowAPIRead.model_validate(show)


def delete_show(s: Session, show_slug: str) -> ShowAPIRead:
    show = (
        s.query(Show)
        .filter_by(slug=show_slug)
        .one_or_none()
    )
    if show is None:
        raise HTTPException(status_code=404, detail="Show not found")

    payload = ShowAPIRead.model_validate(show)
    s.delete(show)
    s.flush()

    event_emitter = events.get_wireloft_event_emitter()
    event_emitter.emit("show_deleted", show.id)

    return payload