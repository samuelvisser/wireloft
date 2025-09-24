from __future__ import annotations

from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.api.helpers import update_database_fields
from backend.api.models.download_profile_podcast import *
from backend.db.models import DownloadProfilePodcast


def get_podcast_download_profiles_list(s: Session) -> list[DownloadProfilePodcastAPIRead]:
    items = (
        s.query(DownloadProfilePodcast)
        .order_by(DownloadProfilePodcast.id)
        .all()
    )
    return [DownloadProfilePodcastAPIRead.model_validate(it) for it in items]


def get_download_profile_podcast(s: Session, download_profile_id: int) -> DownloadProfilePodcastAPIRead:
    item = (
        s.query(DownloadProfilePodcast)
        .filter_by(id=download_profile_id)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Download profile not found")

    return DownloadProfilePodcastAPIRead.model_validate(item)


def create_download_profile_podcast(s: Session, body: DownloadProfilePodcastAPICreate) -> DownloadProfilePodcastAPIRead:
    data = body.model_dump(by_alias=True)
    item = DownloadProfilePodcast(**data)
    s.add(item)
    s.flush()
    return DownloadProfilePodcastAPIRead.model_validate(item)


def update_download_profile_podcast(s: Session, download_profile_id: int, body: DownloadProfilePodcastAPIUpdate) -> DownloadProfilePodcastAPIRead:
    item = (
        s.query(DownloadProfilePodcast)
        .filter_by(id=download_profile_id)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Download profile not found")

    update_database_fields(item, body)
    s.flush()
    return DownloadProfilePodcastAPIRead.model_validate(item)


def delete_download_profile_podcast(s: Session, download_profile_id: int) -> DownloadProfilePodcastAPIRead:
    item = (
        s.query(DownloadProfilePodcast)
        .filter_by(id=download_profile_id)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Download profile not found")

    payload = DownloadProfilePodcastAPIRead.model_validate(item)
    s.delete(item)
    s.flush()
    return payload
