from __future__ import annotations

from fastapi import HTTPException

from backend.api.helpers import update_database_fields
from backend.api.models.media_download import *
from backend.app import db_session
from backend.db.models import MediaDownload


def get_media_downloads_list() -> list[MediaDownloadAPIRead]:
    with db_session() as s:
        items = (
            s.query(MediaDownload)
            .order_by(MediaDownload.id)
            .all()
        )
        return [MediaDownloadAPIRead.model_validate(it) for it in items]


def get_media_download(media_download_id: int) -> MediaDownloadAPIRead:
    with db_session() as s:
        item = (
            s.query(MediaDownload)
            .filter_by(id=media_download_id)
            .one_or_none()
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Media download not found")

        return MediaDownloadAPIRead.model_validate(item)


def create_media_download(body: MediaDownloadAPICreate) -> MediaDownloadAPIRead:
    with db_session() as s:
        data = body.model_dump(by_alias=True)
        item = MediaDownload(**data)
        s.add(item)
        s.commit()
        s.refresh(item)
        return MediaDownloadAPIRead.model_validate(item)


def update_media_download(media_download_id: int, body: MediaDownloadAPIUpdate) -> MediaDownloadAPIRead:
    with db_session() as s:
        item = (
            s.query(MediaDownload)
            .filter_by(id=media_download_id)
            .one_or_none()
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Media download not found")

        update_database_fields(item, body)
        s.commit()
        s.refresh(item)
        return MediaDownloadAPIRead.model_validate(item)


def delete_media_download(media_download_id: int) -> MediaDownloadAPIRead:
    with db_session() as s:
        item = (
            s.query(MediaDownload)
            .filter_by(id=media_download_id)
            .one_or_none()
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Media download not found")

        payload = MediaDownloadAPIRead.model_validate(item)
        s.delete(item)
        s.commit()
        return payload
