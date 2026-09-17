from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.api.helpers import update_database_fields
from backend.api.models.local_media_profile import (
    LocalMediaProfileAPICreate,
    LocalMediaProfileAPIRead,
    LocalMediaProfileAPIUpdate,
)
from backend.db.models import (
    DownloadProfileBase,
    LocalMediaProfileBase,
    MediaDownloadBase,
    MovieLocalMediaProfile,
    ShowLocalMediaProfile,
)
from backend.types.local_media_profile_types import LocalMediaProfileType

from .helpers import ensure_unique_profile_settings


_PROFILE_MODELS = {
    LocalMediaProfileType.SHOW.value: ShowLocalMediaProfile,
    LocalMediaProfileType.MOVIE.value: MovieLocalMediaProfile,
}


def _raise_profile_in_use(message: str) -> None:
    raise HTTPException(
        status_code=409,
        detail=[{
            "loc": ["body", "__all__"],
            "msg": message,
            "type": "resource_in_use",
        }],
    )


def _ensure_local_media_profile_can_be_deleted(
    s: Session,
    local_media_profile: LocalMediaProfileBase,
) -> None:
    has_downloads = (
        s.query(MediaDownloadBase.id)
        .filter(MediaDownloadBase.local_media_profile_id == local_media_profile.id)
        .first()
        is not None
    )
    if has_downloads:
        _raise_profile_in_use(
            "This Local Media Profile cannot be deleted because downloads are still attached to it. "
            "Delete those downloads before deleting the profile."
        )

    has_download_profiles = (
        s.query(DownloadProfileBase.id)
        .filter(DownloadProfileBase.local_media_profile_id == local_media_profile.id)
        .first()
        is not None
    )
    if has_download_profiles:
        _raise_profile_in_use(
            "This Local Media Profile cannot be deleted because one or more Download Profiles still use it. "
            "Change or delete those Download Profiles before deleting the profile."
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
    ensure_unique_profile_settings(s, body)
    data = body.model_dump(by_alias=True)
    if body.type != LocalMediaProfileType.SHOW:
        data.pop("show_scope", None)
    profile_model = _PROFILE_MODELS[body.type]
    mp = profile_model(**data)
    s.add(mp)
    s.flush()
    return LocalMediaProfileAPIRead.model_validate(mp)


def update_local_media_profile(
    s: Session,
    local_media_profile_slug: str,
    body: LocalMediaProfileAPIUpdate,
) -> LocalMediaProfileAPIRead:
    local_media_profile: Optional[LocalMediaProfileBase] = (
        s.query(LocalMediaProfileBase)
        .filter_by(slug=local_media_profile_slug)
        .one_or_none()
    )
    if local_media_profile is None:
        raise HTTPException(status_code=404, detail="Media profile not found")
    if local_media_profile.type != body.type:
        raise HTTPException(status_code=422, detail="A Local Media Profile's type cannot be changed")

    ensure_unique_profile_settings(s, body, exclude_id=local_media_profile.id)
    exclude_fields = {"show_scope"} if local_media_profile.type != LocalMediaProfileType.SHOW.value else None
    update_database_fields(local_media_profile, body, exclude_fields=exclude_fields)
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

    _ensure_local_media_profile_can_be_deleted(s, local_media_profile)

    payload = LocalMediaProfileAPIRead.model_validate(local_media_profile)
    s.delete(local_media_profile)
    s.flush()
    return payload
