from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.api.helpers import update_database_fields
from backend.api.models.local_media_profile import *
from backend.db.models import (
    LocalMediaProfileBase,
    MovieLocalMediaProfile,
    ShowLocalMediaProfile,
)
from backend.types.local_media_profile_types import LocalMediaProfileType


_PROFILE_MODELS = {
    LocalMediaProfileType.SHOW.value: ShowLocalMediaProfile,
    LocalMediaProfileType.MOVIE.value: MovieLocalMediaProfile,
}


def _ensure_unique_profile_settings(
    s: Session,
    body: LocalMediaProfileAPICreate | LocalMediaProfileAPIUpdate,
    *,
    exclude_id: int | None = None,
) -> None:
    query = s.query(LocalMediaProfileBase).filter(
        LocalMediaProfileBase.type == body.type,
        LocalMediaProfileBase.output_template == body.output_template,
        LocalMediaProfileBase.preferred_format == body.preferred_format,
        LocalMediaProfileBase.append_media_type_to_filename == body.append_media_type_to_filename,
    )
    if exclude_id is not None:
        query = query.filter(LocalMediaProfileBase.id != exclude_id)
    if query.first() is not None:
        raise HTTPException(
            status_code=409,
            detail=[{
                "loc": ["body", "outputTemplate"],
                "msg": "A Local Media Profile with this type, output path template, preferred format, and media-type filename setting already exists",
                "type": "unique_violation",
            }],
        )


def get_local_media_profiles_list(s: Session) -> list[LocalMediaProfileAPIRead]:
    local_media_profiles = (
        s.query(LocalMediaProfileBase)
        .order_by(LocalMediaProfileBase.id)
        .all()
    )
    return [LocalMediaProfileAPIRead.model_validate(mp) for mp in local_media_profiles]


def get_local_media_profile(s: Session, local_media_profile_slug: str) -> LocalMediaProfileAPIRead:
    local_media_profile = (
        s.query(LocalMediaProfileBase)
        .filter_by(slug=local_media_profile_slug)
        .one_or_none()
    )
    if local_media_profile is None:
        raise HTTPException(status_code=404, detail="Media profile not found")
    return LocalMediaProfileAPIRead.model_validate(local_media_profile)


def create_local_media_profile(s: Session, body: LocalMediaProfileAPICreate) -> LocalMediaProfileAPIRead:
    _ensure_unique_profile_settings(s, body)
    data = body.model_dump(by_alias=True)
    profile_model = _PROFILE_MODELS[body.type]
    mp = profile_model(**data)
    s.add(mp)
    s.flush()
    return LocalMediaProfileAPIRead.model_validate(mp)


def update_local_media_profile(s: Session, local_media_profile_slug: str, body: LocalMediaProfileAPIUpdate) -> LocalMediaProfileAPIRead:
    local_media_profile: Optional[LocalMediaProfileBase] = (
        s.query(LocalMediaProfileBase)
        .filter_by(slug=local_media_profile_slug)
        .one_or_none()
    )
    if local_media_profile is None:
        raise HTTPException(status_code=404, detail="Media profile not found")
    if local_media_profile.type != body.type:
        raise HTTPException(status_code=422, detail="A Local Media Profile's type cannot be changed")

    _ensure_unique_profile_settings(s, body, exclude_id=local_media_profile.id)
    update_database_fields(local_media_profile, body)
    s.flush()
    return LocalMediaProfileAPIRead.model_validate(local_media_profile)


def delete_local_media_profile(s: Session, local_media_profile_slug: str) -> LocalMediaProfileAPIRead:
    local_media_profile = (
        s.query(LocalMediaProfileBase)
        .filter_by(slug=local_media_profile_slug)
        .one_or_none()
    )
    if local_media_profile is None:
        raise HTTPException(status_code=404, detail="Media profile not found")

    payload = LocalMediaProfileAPIRead.model_validate(local_media_profile)
    s.delete(local_media_profile)
    s.flush()
    return payload
