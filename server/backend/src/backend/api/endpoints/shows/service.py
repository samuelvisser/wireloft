from __future__ import annotations

import json
from typing import Optional
from uuid import uuid4

from sqlalchemy.orm import Session
from backend.api.helpers import update_database_fields
from backend.api.models.show import *

from fastapi import HTTPException

from backend.db.models import Show
from task_manager.events.transactional import queue_event


SYNC_LOG_META_KEY = "episode_sync_log"
SYNC_LOG_LIMIT = 10


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

    queue_event(s, "show.added", {
        "resource_id": show.id,
        "id": show.id,
        "slug": show.slug,
        "title": show.title,
    })

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

    queue_event(s, "show.updated", {
        "resource_id": show.id,
        "id": show.id,
        "slug": show.slug,
    })

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

    queue_event(s, "show.deleted", {
        "resource_id": show.id,
        "id": show.id,
        "slug": show.slug,
    })

    s.delete(show)
    s.flush()

    return payload


def request_show_sync(s: Session, show_slug: str) -> dict[str, bool | str]:
    show = (
        s.query(Show)
        .filter_by(slug=show_slug)
        .one_or_none()
    )
    if show is None:
        raise HTTPException(status_code=404, detail="Show not found")

    request_id = str(uuid4())
    queue_event(s, "show.sync_requested", {
        "resource_id": show.id,
        "id": show.id,
        "slug": show.slug,
        "manual_request_id": request_id,
    })
    return {"queued": True, "request_id": request_id}


def get_show_sync_log(s: Session, show_slug: str) -> list[dict]:
    show = (
        s.query(Show)
        .filter_by(slug=show_slug)
        .one_or_none()
    )
    if show is None:
        raise HTTPException(status_code=404, detail="Show not found")

    raw = show.get_meta(SYNC_LOG_META_KEY)
    if not raw:
        return []

    try:
        history = json.loads(raw)
    except (TypeError, ValueError):
        return []

    if not isinstance(history, list):
        return []
    return history[:SYNC_LOG_LIMIT]
