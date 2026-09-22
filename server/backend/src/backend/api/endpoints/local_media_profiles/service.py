from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.db.models import (
    DownloadProfileBase,
    LocalMediaProfileBase,
    MediaDownloadBase,
)


def _raise_profile_in_use(message: str) -> None:
    raise HTTPException(
        status_code=409,
        detail=[{
            "loc": ["body", "__all__"],
            "msg": message,
            "type": "resource_in_use",
        }],
    )


def ensure_local_media_profile_can_be_deleted(
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


def get_local_media_profiles_list(s: Session) -> list[LocalMediaProfileBase]:
    return (
        s.query(LocalMediaProfileBase)
        .order_by(LocalMediaProfileBase.id)
        .all()
    )


def get_local_media_profile(
    s: Session,
    local_media_profile_slug: str,
) -> LocalMediaProfileBase:
    local_media_profile = (
        s.query(LocalMediaProfileBase)
        .filter_by(slug=local_media_profile_slug)
        .one_or_none()
    )
    if local_media_profile is None:
        raise HTTPException(status_code=404, detail="Media profile not found")
    return local_media_profile


def delete_local_media_profile_record(
    s: Session,
    local_media_profile: LocalMediaProfileBase,
) -> None:
    ensure_local_media_profile_can_be_deleted(s, local_media_profile)
    s.delete(local_media_profile)
    s.flush()
