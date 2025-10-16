from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.api.helpers import update_database_fields
from backend.api.models.local_media_profile import *
from backend.db.models import LocalMediaProfile


def get_local_media_profiles_list(s: Session) -> list[LocalMediaProfileAPIRead]:
    local_media_profiles = (
        s.query(LocalMediaProfile)
        .order_by(LocalMediaProfile.id)
        .all()
    )
    
    return [LocalMediaProfileAPIRead.model_validate(mp) for mp in local_media_profiles]


def get_local_media_profile(s: Session, local_media_profile_slug: str) -> LocalMediaProfileAPIRead:
    local_media_profile = (
        s.query(LocalMediaProfile)
        .filter_by(slug=local_media_profile_slug)
        .one_or_none()
    )
    if local_media_profile is None:
        raise HTTPException(status_code=404, detail="Media profile not found")

    return LocalMediaProfileAPIRead.model_validate(local_media_profile)


def create_local_media_profile(s: Session, body: LocalMediaProfileAPICreate) -> LocalMediaProfileAPIRead:
    # Build model from validated Pydantic data
    data = body.model_dump(by_alias=True)

    mp = LocalMediaProfile(**data)
    s.add(mp)
    s.flush()
    return LocalMediaProfileAPIRead.model_validate(mp)


def update_local_media_profile(s: Session, local_media_profile_slug: str, body: LocalMediaProfileAPIUpdate) -> LocalMediaProfileAPIRead:
    local_media_profile: Optional[LocalMediaProfile] = (
        s.query(LocalMediaProfile)
        .filter_by(slug=local_media_profile_slug)
        .one_or_none()
    )
    if local_media_profile is None:
        raise HTTPException(status_code=404, detail="Media profile not found")

    # Apply updates and flush
    update_database_fields(local_media_profile, body)
    s.flush()
    return LocalMediaProfileAPIRead.model_validate(local_media_profile)


def delete_local_media_profile(s: Session, local_media_profile_slug: str) -> LocalMediaProfileAPIRead:
    local_media_profile = (
        s.query(LocalMediaProfile)
        .filter_by(slug=local_media_profile_slug)
        .one_or_none()
    )
    if local_media_profile is None:
        raise HTTPException(status_code=404, detail="Media profile not found")

    payload = LocalMediaProfileAPIRead.model_validate(local_media_profile)
    s.delete(local_media_profile)
    s.flush()
    return payload