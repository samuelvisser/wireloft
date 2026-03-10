from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.api.helpers import update_database_fields
from backend.api.models.podcast_download_profile import *
from backend.db.models.download_profile import PodcastDownloadProfile
from task_manager.events.emitters import emit_event


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
    data = body.model_dump(by_alias=True)
    item = PodcastDownloadProfile(**data)
    s.add(item)
    s.flush()

    emit_event("download_profile.added", {
        "resource_id": item.id,
        "id": item.id,
        "name": item.name
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

    update_database_fields(item, body)
    s.flush()
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

    emit_event("download_profile.deleted", {
        "resource_id": item.id,
        "id": item.id
    })

    s.delete(item)
    s.flush()
    return payload
