from __future__ import annotations

from fastapi import HTTPException
from pydantic import TypeAdapter
from sqlalchemy.orm import Session, with_polymorphic

from backend.api.models.local_media_profile_view import LocalMediaProfileAPIRead

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
            "This Local Media Profile cannot be deleted because persistent download history is attached to it."
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


_local_media_profile_read_adapter = TypeAdapter(LocalMediaProfileAPIRead)


def _to_read(local_media_profile: LocalMediaProfileBase) -> LocalMediaProfileAPIRead:
    return _local_media_profile_read_adapter.validate_python(
        local_media_profile,
        from_attributes=True,
    )


def get_local_media_profiles_list(s: Session) -> list[LocalMediaProfileAPIRead]:
    profile = with_polymorphic(LocalMediaProfileBase, "*")
    items = (
        s.query(profile)
        .order_by(profile.id)
        .all()
    )
    return [_to_read(item) for item in items]


def get_local_media_profile(
    s: Session,
    local_media_profile_slug: str,
) -> LocalMediaProfileAPIRead:
    profile = with_polymorphic(LocalMediaProfileBase, "*")
    local_media_profile = (
        s.query(profile)
        .filter(profile.slug == local_media_profile_slug)
        .one_or_none()
    )
    if local_media_profile is None:
        raise HTTPException(status_code=404, detail="Media profile not found")
    return _to_read(local_media_profile)


def delete_local_media_profile_record(
    s: Session,
    local_media_profile: LocalMediaProfileBase,
) -> None:
    ensure_local_media_profile_can_be_deleted(s, local_media_profile)
    s.delete(local_media_profile)
    s.flush()
