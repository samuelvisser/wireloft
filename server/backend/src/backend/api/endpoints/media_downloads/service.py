from __future__ import annotations

from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.api.helpers import update_database_fields
from backend.api.models.media_download import *
from backend.db.models.media_download import MediaDownloadBase


def get_media_downloads_list(s: Session) -> list[MediaDownloadAPIRead]:
    items = (
        s.query(MediaDownloadBase)
        .order_by(MediaDownloadBase.id)
        .all()
    )
    return [MediaDownloadAPIRead.model_validate(it) for it in items]


def get_media_download(s: Session, media_download_id: int) -> MediaDownloadAPIRead:
    item = (
        s.query(MediaDownloadBase)
        .filter_by(id=media_download_id)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Media download not found")

    return MediaDownloadAPIRead.model_validate(item)


def create_media_download(s: Session, body: MediaDownloadAPICreate) -> MediaDownloadAPIRead:
    data = body.model_dump(by_alias=True)
    item = MediaDownloadBase(**data)
    s.add(item)
    s.flush()
    return MediaDownloadAPIRead.model_validate(item)


def update_media_download(s: Session, media_download_id: int, body: MediaDownloadAPIUpdate) -> MediaDownloadAPIRead:
    item = (
        s.query(MediaDownloadBase)
        .filter_by(id=media_download_id)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Media download not found")

    update_database_fields(item, body)
    s.flush()
    return MediaDownloadAPIRead.model_validate(item)


def delete_media_download(s: Session, media_download_id: int) -> MediaDownloadAPIRead:
    item = (
        s.query(MediaDownloadBase)
        .filter_by(id=media_download_id)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Media download not found")

    payload = MediaDownloadAPIRead.model_validate(item)
    s.delete(item)
    s.flush()
    return payload
