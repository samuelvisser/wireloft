from fastapi import APIRouter, status

from .service import *
from ...models.media_download import *
from ...app import db_session

router = APIRouter()

@router.get("", response_model=list[MediaDownloadAPIRead])
def media_downloads_list():
    with db_session() as s:
        return get_media_downloads_list(s)


@router.post("", response_model=MediaDownloadAPIRead, status_code=status.HTTP_201_CREATED)
def media_downloads_create(body: MediaDownloadAPICreate):
    with db_session() as s:
        try:
            result = create_media_download(s, body)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.get("/{media_download_id}", response_model=MediaDownloadAPIRead)
def media_downloads_detail(media_download_id: int):
    with db_session() as s:
        return get_media_download(s, media_download_id)


@router.patch("/{media_download_id}", response_model=MediaDownloadAPIRead)
def media_downloads_update(media_download_id: int, body: MediaDownloadAPIUpdate):
    with db_session() as s:
        try:
            result = update_media_download(s, media_download_id, body)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.delete("/{media_download_id}", response_model=MediaDownloadAPIRead)
def media_downloads_delete(media_download_id: int):
    with db_session() as s:
        try:
            result = delete_media_download(s, media_download_id)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise
