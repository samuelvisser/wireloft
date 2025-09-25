from __future__ import annotations

from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.api.helpers import update_database_fields
from backend.api.models.media_profile import *
from backend.db.models import MediaProfile


def get_media_profiles_list(s: Session) -> list[MediaProfileAPIRead]:
    media_profiles = (
        s.query(MediaProfile)
        .order_by(MediaProfile.id)
        .all()
    )
    
    return [MediaProfileAPIRead.model_validate(mp) for mp in media_profiles]


def get_media_profile(s: Session, media_profile_slug: str) -> MediaProfileAPIRead:
    media_profile = (
        s.query(MediaProfile)
        .filter_by(slug=media_profile_slug)
        .one_or_none()
    )
    if media_profile is None:
        raise HTTPException(status_code=404, detail="Media profile not found")

    return MediaProfileAPIRead.model_validate(media_profile)


def create_media_profile(s: Session, body: MediaProfileAPICreate) -> MediaProfileAPIRead:
    # Build model from validated Pydantic data
    data = body.model_dump(by_alias=True)

    mp = MediaProfile(**data)
    s.add(mp)
    s.flush()
    return MediaProfileAPIRead.model_validate(mp)


def update_media_profile(s: Session, media_profile_slug: str, body: MediaProfileAPIUpdate) -> MediaProfileAPIRead:
    media_profile = (
        s.query(MediaProfile)
        .filter_by(slug=media_profile_slug)
        .one_or_none()
    )
    if media_profile is None:
        raise HTTPException(status_code=404, detail="Media profile not found")

    # Apply updates and flush
    update_database_fields(media_profile, body)
    s.flush()
    return MediaProfileAPIRead.model_validate(media_profile)


def delete_media_profile(s: Session, media_profile_slug: str) -> MediaProfileAPIRead:
    media_profile = (
        s.query(MediaProfile)
        .filter_by(slug=media_profile_slug)
        .one_or_none()
    )
    if media_profile is None:
        raise HTTPException(status_code=404, detail="Media profile not found")

    payload = MediaProfileAPIRead.model_validate(media_profile)
    s.delete(media_profile)
    s.flush()
    return payload