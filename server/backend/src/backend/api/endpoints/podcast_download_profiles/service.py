from __future__ import annotations

from fastapi import HTTPException

from backend.api.helpers import update_database_fields
from backend.api.models.download_profile_podcast import *
from backend.app import db_session
from backend.db.models import DownloadProfilePodcast


def get_podcast_download_profiles_list() -> list[DownloadProfilePodcastAPIRead]:
    with db_session() as s:
        items = (
            s.query(DownloadProfilePodcast)
            .order_by(DownloadProfilePodcast.id)
            .all()
        )
        return [DownloadProfilePodcastAPIRead.model_validate(it) for it in items]


def get_download_profile_podcast(download_profile_id: int) -> DownloadProfilePodcastAPIRead:
    with db_session() as s:
        item = (
            s.query(DownloadProfilePodcast)
            .filter_by(id=download_profile_id)
            .one_or_none()
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Download profile not found")

        return DownloadProfilePodcastAPIRead.model_validate(item)


def create_download_profile_podcast(body: DownloadProfilePodcastAPICreate) -> DownloadProfilePodcastAPIRead:
    with db_session() as s:
        data = body.model_dump(by_alias=True)
        item = DownloadProfilePodcast(**data)
        s.add(item)
        s.commit()
        s.refresh(item)
        return DownloadProfilePodcastAPIRead.model_validate(item)


def update_download_profile_podcast(download_profile_id: int, body: DownloadProfilePodcastAPIUpdate) -> DownloadProfilePodcastAPIRead:
    with db_session() as s:
        item = (
            s.query(DownloadProfilePodcast)
            .filter_by(id=download_profile_id)
            .one_or_none()
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Download profile not found")

        update_database_fields(item, body)
        s.commit()
        s.refresh(item)
        return DownloadProfilePodcastAPIRead.model_validate(item)


def delete_download_profile_podcast(download_profile_id: int) -> DownloadProfilePodcastAPIRead:
    with db_session() as s:
        item = (
            s.query(DownloadProfilePodcast)
            .filter_by(id=download_profile_id)
            .one_or_none()
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Download profile not found")

        payload = DownloadProfilePodcastAPIRead.model_validate(item)
        s.delete(item)
        s.commit()
        return payload
