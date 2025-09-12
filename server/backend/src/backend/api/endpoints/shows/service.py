from __future__ import annotations

from backend.api.helpers import update_database_fields
from backend.api.models.show import *

from fastapi import HTTPException

from backend.app import db_session
from backend.db.models import Show


def get_shows_list() -> list[ShowAPIRead]:
    with db_session() as s:
        shows = (
            s.query(Show)
            .order_by(Show.title.asc())
            .all()
        )
        return [ShowAPIRead.model_validate(show, from_attributes=True) for show in shows]


def get_show(show_slug: str) -> ShowAPIRead:
    with db_session() as s:
        show = (
            s.query(Show)
            .filter_by(slug=show_slug)
            .one_or_none()
        )

        if show is None:
            raise HTTPException(status_code=404, detail="Show not found")

        return ShowAPIRead.model_validate(show, from_attributes=True)


def create_show(body: ShowAPICreate) -> ShowAPIRead:
    with db_session() as s:
        # Build model from validated Pydantic data
        data = body.model_dump(by_alias=True)

        show = Show(**data)
        s.add(show)
        s.commit()
        s.refresh(show)
        return ShowAPIRead.model_validate(show, from_attributes=True)


def update_show(show_slug: str, body: ShowAPIUpdate) -> ShowAPIRead:
    with db_session() as s:
        show = (
            s.query(Show)
            .filter_by(slug=show_slug)
            .one_or_none()
        )
        if show is None:
            raise HTTPException(status_code=404, detail="Show not found")

        # Commit and return
        update_database_fields(show, body)
        s.commit()
        s.refresh(show)
        return ShowAPIRead.model_validate(show, from_attributes=True)


def delete_show(show_slug: str) -> ShowAPIRead:
    with db_session() as s:
        show = (
            s.query(Show)
            .filter_by(slug=show_slug)
            .one_or_none()
        )
        if show is None:
            raise HTTPException(status_code=404, detail="Show not found")

        payload = ShowAPIRead.model_validate(show, from_attributes=True)
        s.delete(show)
        s.commit()
        return payload