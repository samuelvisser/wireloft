from __future__ import annotations

from sqlalchemy.orm import Session, joinedload, with_polymorphic
from fastapi import HTTPException

from backend.api.models.stream_profile import StreamProfileAPIReadView, StreamProfileAPIRead
from backend.api.models.rss_stream_profile import RssStreamProfileAPIRead
from backend.types.stream_profile_types import StreamProfileType
from backend.db.models import StreamProfileBase, Show, RssStreamProfile


def _to_view(item: StreamProfileBase) -> StreamProfileAPIReadView:
    base = StreamProfileAPIRead.model_validate(item).model_dump()
    show_title = item.show.title if getattr(item, "show", None) is not None else None
    show_slug = item.show.slug if getattr(item, "show", None) is not None else None

    # Map concrete implementation payload based on type discriminator
    t = str(getattr(item, "type", ""))
    if t == StreamProfileType.RSS.value:
        impl = RssStreamProfileAPIRead.model_validate(item)
    else:
        # This will fail Pydantic validation, which is what we want; there always needs to be an implementation
        impl = None

    return StreamProfileAPIReadView.model_validate({
        **base,
        "show_title": show_title or "",
        "show_slug": show_slug or "",
        "stream_profile_impl": impl,
    })


def get_stream_profile_views_list(s: Session) -> list[StreamProfileAPIReadView]:
    SP = with_polymorphic(StreamProfileBase, [RssStreamProfile])
    items = (
        s.query(SP)
        .options(
            joinedload(SP.show),
        )
        .join(Show, Show.id == SP.show_id)
        .order_by(Show.title.asc(), SP.id.asc())
        .all()
    )
    return [_to_view(it) for it in items]


def get_stream_profile_view(s: Session, stream_profile_id: int) -> StreamProfileAPIReadView:
    SP = with_polymorphic(StreamProfileBase, [RssStreamProfile])
    item = (
        s.query(SP)
        .options(
            joinedload(SP.show),
        )
        .filter(SP.id == stream_profile_id)
        .one_or_none()
    )

    if item is None:
        raise HTTPException(status_code=404, detail="Stream profile not found")

    return _to_view(item)
