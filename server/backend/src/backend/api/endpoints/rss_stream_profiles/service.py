from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.api.helpers import update_database_fields
from backend.api.models.rss_stream_profile import *
from backend.db.models.stream_profile import RssStreamProfile


def get_rss_stream_profiles_list(s: Session) -> list[RssStreamProfileAPIRead]:
    items = (
        s.query(RssStreamProfile)
        .order_by(RssStreamProfile.id)
        .all()
    )
    return [RssStreamProfileAPIRead.model_validate(it) for it in items]


def get_stream_profile_rss(s: Session, stream_profile_id: int) -> RssStreamProfileAPIRead:
    item = (
        s.query(RssStreamProfile)
        .filter_by(id=stream_profile_id)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Stream profile not found")

    return RssStreamProfileAPIRead.model_validate(item)


def create_stream_profile_rss(s: Session, body: RssStreamProfileAPICreate) -> RssStreamProfileAPIRead:
    data = body.model_dump(by_alias=True)
    item = RssStreamProfile(**data)
    s.add(item)
    s.flush()
    return RssStreamProfileAPIRead.model_validate(item)


def update_stream_profile_rss(s: Session, stream_profile_id: int, body: RssStreamProfileAPIUpdate) -> RssStreamProfileAPIRead:
    item: Optional[RssStreamProfile] = (
        s.query(RssStreamProfile)
        .filter_by(id=stream_profile_id)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Stream profile not found")

    update_database_fields(item, body)
    s.flush()
    return RssStreamProfileAPIRead.model_validate(item)


def delete_stream_profile_rss(s: Session, stream_profile_id: int) -> RssStreamProfileAPIRead:
    item = (
        s.query(RssStreamProfile)
        .filter_by(id=stream_profile_id)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Stream profile not found")

    payload = RssStreamProfileAPIRead.model_validate(item)
    s.delete(item)
    s.flush()
    return payload
