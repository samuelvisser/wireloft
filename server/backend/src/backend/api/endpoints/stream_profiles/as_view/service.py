from __future__ import annotations

from dataclasses import dataclass
from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload, with_polymorphic
from sqlalchemy.orm.util import AliasedClass

from backend.api.models.stream_profile import StreamProfileAPIReadView
from backend.db.models import RssStreamProfile, Show, StreamProfileBase


@dataclass(frozen=True)
class _StreamProfileViewSource:
    profile: AliasedClass[StreamProfileBase]


def _to_view(item: AliasedClass[StreamProfileBase]) -> StreamProfileAPIReadView:
    return StreamProfileAPIReadView.model_validate(
        _StreamProfileViewSource(profile=item)
    )


def get_stream_profile_views_list(s: Session) -> list[StreamProfileAPIReadView]:
    profile = with_polymorphic(StreamProfileBase, [RssStreamProfile])
    items = (
        s.query(profile)
        .options(joinedload(profile.show))
        .join(Show, Show.id == profile.show_id)
        .order_by(Show.title.asc(), profile.id.asc())
        .all()
    )
    return [_to_view(item) for item in items]


def get_stream_profile_view(
    s: Session,
    stream_profile_id: int,
) -> StreamProfileAPIReadView:
    profile = with_polymorphic(StreamProfileBase, [RssStreamProfile])
    item = (
        s.query(profile)
        .options(joinedload(profile.show))
        .filter_by(id=stream_profile_id)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Stream profile not found")
    return _to_view(item)
