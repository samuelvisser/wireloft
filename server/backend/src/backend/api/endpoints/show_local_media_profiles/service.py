from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.api.endpoints.local_media_profiles.helpers import ensure_unique_profile_settings
from backend.api.endpoints.local_media_profiles.service import delete_local_media_profile_record
from backend.api.models.show_local_media_profile import (
    ShowLocalMediaProfileAPICreate,
    ShowLocalMediaProfileAPIRead,
    ShowLocalMediaProfileAPIUpdate,
)
from backend.db.model_mapping import create_database_fields, update_database_fields
from backend.db.models import ShowLocalMediaProfile


def get_show_local_media_profiles_list(
    s: Session,
) -> list[ShowLocalMediaProfileAPIRead]:
    items = (
        s.query(ShowLocalMediaProfile)
        .order_by(ShowLocalMediaProfile.id)
        .all()
    )
    return [ShowLocalMediaProfileAPIRead.model_validate(item) for item in items]


def get_show_local_media_profile(
    s: Session,
    local_media_profile_slug: str,
) -> ShowLocalMediaProfileAPIRead:
    item: Optional[ShowLocalMediaProfile] = (
        s.query(ShowLocalMediaProfile)
        .filter_by(slug=local_media_profile_slug)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Show Local Media Profile not found")
    return ShowLocalMediaProfileAPIRead.model_validate(item)


def create_show_local_media_profile(
    s: Session,
    body: ShowLocalMediaProfileAPICreate,
) -> ShowLocalMediaProfileAPIRead:
    ensure_unique_profile_settings(s, ShowLocalMediaProfile, body)
    item = create_database_fields(ShowLocalMediaProfile, body)
    s.add(item)
    s.flush()
    return ShowLocalMediaProfileAPIRead.model_validate(item)


def update_show_local_media_profile(
    s: Session,
    local_media_profile_slug: str,
    body: ShowLocalMediaProfileAPIUpdate,
) -> ShowLocalMediaProfileAPIRead:
    item: Optional[ShowLocalMediaProfile] = (
        s.query(ShowLocalMediaProfile)
        .filter_by(slug=local_media_profile_slug)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Show Local Media Profile not found")

    ensure_unique_profile_settings(
        s,
        ShowLocalMediaProfile,
        body,
        exclude_id=item.id,
    )
    update_database_fields(item, body)
    s.flush()
    return ShowLocalMediaProfileAPIRead.model_validate(item)


def delete_show_local_media_profile(
    s: Session,
    local_media_profile_slug: str,
) -> ShowLocalMediaProfileAPIRead:
    item: Optional[ShowLocalMediaProfile] = (
        s.query(ShowLocalMediaProfile)
        .filter_by(slug=local_media_profile_slug)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Show Local Media Profile not found")

    payload = ShowLocalMediaProfileAPIRead.model_validate(item)
    delete_local_media_profile_record(s, item)
    return payload
