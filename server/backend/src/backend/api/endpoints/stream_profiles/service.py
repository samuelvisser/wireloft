from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session, with_polymorphic
from fastapi import HTTPException

from backend.api.models.stream_profile import StreamProfileAPIRead
from backend.api.models.rss_stream_profile import RssStreamProfileAPIRead
from backend.types.stream_profile_types import StreamProfileType
from backend.db.models import StreamProfileBase, RssStreamProfile


def get_stream_profiles_list(s: Session, show_slug: Optional[str] = None) -> list[StreamProfileAPIRead]:
    SP = with_polymorphic(StreamProfileBase, [RssStreamProfile])
    if show_slug is not None:
        items = (
            s.query(SP)
            .filter(
                SP.show.has(slug=show_slug)
            )
            .order_by(SP.id.asc())
            .all()
        )
    else:
        items = (
            s.query(SP)
            .order_by(SP.id.asc())
            .all()
        )
    return [StreamProfileAPIRead.model_validate(it) for it in items]


def get_stream_profile(s: Session, stream_profile_id: int) -> StreamProfileAPIRead:
    SP = with_polymorphic(StreamProfileBase, [RssStreamProfile])
    item = (
        s.query(SP)
        .filter(SP.id == stream_profile_id)
        .one_or_none()
    )

    if item is None:
        raise HTTPException(status_code=404, detail="Stream profile not found")

    return StreamProfileAPIRead.model_validate(item)
