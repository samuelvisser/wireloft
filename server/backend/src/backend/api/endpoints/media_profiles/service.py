from __future__ import annotations

from fastapi import HTTPException

from backend.api.helpers import update_database_fields
from backend.api.models.media_profile import *
from backend.app import db_session
from backend.db.models import MediaProfile


def get_media_profiles_list() -> list[MediaProfileAPIRead]:
    with db_session() as s:
        media_profiles = (
            s.query(MediaProfile)
            .order_by(MediaProfile.id)
            .all()
        )
        return [MediaProfileAPIRead.model_validate(mp, from_attributes=True) for mp in media_profiles]


def get_media_profile(media_profile_slug: str) -> MediaProfileAPIRead:
    with db_session() as s:
        media_profile = (
            s.query(MediaProfile)
            .filter_by(slug=media_profile_slug)
            .one_or_none()
        )
        if media_profile is None:
            raise HTTPException(status_code=404, detail="Media profile not found")

        return MediaProfileAPIRead.model_validate(media_profile, from_attributes=True)


def create_media_profile(body: MediaProfileAPICreate) -> MediaProfileAPIRead:
    with db_session() as s:
        # Build model from validated Pydantic data
        data = body.model_dump(by_alias=True)

        mp = MediaProfile(**data)
        s.add(mp)
        s.commit()
        s.refresh(mp)
        return MediaProfileAPIRead.model_validate(mp, from_attributes=True)


def update_media_profile(media_profile_slug: str, body: MediaProfileAPIUpdate) -> MediaProfileAPIRead:
    with db_session() as s:
        media_profile = (
            s.query(MediaProfile)
            .filter_by(slug=media_profile_slug)
            .one_or_none()
        )
        if media_profile is None:
            raise HTTPException(status_code=404, detail="Media profile not found")

        # Commit and return
        update_database_fields(media_profile, body)
        s.commit()
        s.refresh(media_profile)
        return MediaProfileAPIRead.model_validate(media_profile, from_attributes=True)


def delete_media_profile(media_profile_slug: str) -> MediaProfileAPIRead:
    with db_session() as s:
        media_profile = (
            s.query(MediaProfile)
            .filter_by(slug=media_profile_slug)
            .one_or_none()
        )
        if media_profile is None:
            raise HTTPException(status_code=404, detail="Media profile not found")

        payload = MediaProfileAPIRead.model_validate(media_profile, from_attributes=True)
        s.delete(media_profile)
        s.commit()
        return payload