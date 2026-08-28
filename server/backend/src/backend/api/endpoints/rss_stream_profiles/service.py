from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session
from fastapi import HTTPException, Request

from backend.api.helpers import update_database_fields
from backend.api.models.rss_stream_profile import *
from backend.db.models import Show
from backend.db.models.stream_profile import RssStreamProfile
from backend.utils.feed_urls import build_rss_feed_url
from backend.utils.helpers import generate_stream_profile_token


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


def create_stream_profile_rss(s: Session, request: Request, body: RssStreamProfileAPICreate) -> RssStreamProfileAPIRead:
    show: Optional[Show] = s.get(Show, body.show_id)
    if show is None:
        raise HTTPException(status_code=404, detail="Show not found")

    data = body.model_dump(by_alias=True)
    feed_url = (data.pop("feed_url", None) or "").strip()
    # Generated up front (rather than left to the column default) so it's
    # known in time to build the auto-generated feed_url below.
    token = generate_stream_profile_token()

    item = RssStreamProfile(
        **data,
        token=token,
        feed_url=feed_url or build_rss_feed_url(request, token=token, show_slug=show.slug),
    )
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


def regenerate_stream_profile_rss_token(s: Session, request: Request, stream_profile_id: int) -> RssStreamProfileAPIRead:
    """Rotate a profile's secret token, invalidating its previous feed/media URLs.

    Useful if a feed URL has leaked. The displayed feed_url is regenerated to
    match unless it was already edited away from the WireLoft-generated form,
    in which case only its token segment is swapped so a custom hostname the
    user set survives the rotation.
    """
    item: Optional[RssStreamProfile] = (
        s.query(RssStreamProfile)
        .filter_by(id=stream_profile_id)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Stream profile not found")

    old_token = item.token
    item.token = generate_stream_profile_token()
    if old_token in item.feed_url:
        item.feed_url = item.feed_url.replace(old_token, item.token)
    else:
        item.feed_url = build_rss_feed_url(request, token=item.token, show_slug=item.show.slug)
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
