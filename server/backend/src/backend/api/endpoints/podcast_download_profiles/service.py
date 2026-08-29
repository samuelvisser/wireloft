from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.api.helpers import update_database_fields
from backend.api.models.podcast_download_profile import *
from backend.db.models.download_profile import PodcastDownloadProfile
from backend.types.local_media_profile_types import LocalMediaProfileType
from backend.utils.local_media_profiles import require_local_media_profile_type
from task_manager.events.transactional import queue_event


def get_podcast_download_profiles_list(s: Session) -> list[PodcastDownloadProfileAPIRead]:
    items = (
        s.query(PodcastDownloadProfile)
        .order_by(PodcastDownloadProfile.id)
        .all()
    )
    return [PodcastDownloadProfileAPIRead.model_validate(it) for it in items]


def get_download_profile_podcast(s: Session, download_profile_id: int) -> PodcastDownloadProfileAPIRead:
    item = (
        s.query(PodcastDownloadProfile)
        .filter_by(id=download_profile_id)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Download profile not found")

    return PodcastDownloadProfileAPIRead.model_validate(item)


def create_download_profile_podcast(s: Session, body: PodcastDownloadProfileAPICreate) -> PodcastDownloadProfileAPIRead:
    require_local_media_profile_type(s, body.local_media_profile_id, LocalMediaProfileType.SHOW)
    data = body.model_dump(by_alias=True)
    item = PodcastDownloadProfile(**data)
    s.add(item)
    s.flush()

    queue_event(s, "download_profile.added", {
        "resource_id": item.id,
        "id": item.id,
        "show_id": item.show_id,
        "profile_type": item.type,
    })

    return PodcastDownloadProfileAPIRead.model_validate(item)


def update_download_profile_podcast(s: Session, download_profile_id: int, body: PodcastDownloadProfileAPIUpdate) -> PodcastDownloadProfileAPIRead:
    item: Optional[PodcastDownloadProfile] = (
        s.query(PodcastDownloadProfile)
        .filter_by(id=download_profile_id)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Download profile not found")

    require_local_media_profile_type(s, body.local_media_profile_id, LocalMediaProfileType.SHOW)
    update_database_fields(item, body)
    s.flush()

    queue_event(s, "download_profile.updated", {
        "resource_id": item.id,
        "id": item.id,
        "show_id": item.show_id,
        "profile_type": item.type,
    })

    return PodcastDownloadProfileAPIRead.model_validate(item)


def delete_download_profile_podcast(s: Session, download_profile_id: int) -> PodcastDownloadProfileAPIRead:
    item = (
        s.query(PodcastDownloadProfile)
        .filter_by(id=download_profile_id)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Download profile not found")

    payload = PodcastDownloadProfileAPIRead.model_validate(item)

    queue_event(s, "download_profile.deleted", {
        "resource_id": item.id,
        "id": item.id,
        "show_id": item.show_id,
        "profile_type": item.type,
    })

    s.delete(item)
    s.flush()
    return payload
