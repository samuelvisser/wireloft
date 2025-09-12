from fastapi import APIRouter

from .service import *
from ...models.media_download import *

router = APIRouter()

@router.get("", response_model=list[MediaDownloadAPIRead])
def media_downloads_list():
    return get_media_downloads_list()


@router.post("", response_model=MediaDownloadAPIRead)
def media_downloads_create(body: MediaDownloadAPICreate):
    return create_media_download(body)


@router.get("/{media_download_id}", response_model=MediaDownloadAPIRead)
def media_downloads_detail(media_download_id: int):
    return get_media_download(media_download_id)


@router.patch("/{media_download_id}", response_model=MediaDownloadAPIRead)
def media_downloads_update(media_download_id: int, body: MediaDownloadAPIUpdate):
    return update_media_download(media_download_id, body)


@router.delete("/{media_download_id}", response_model=MediaDownloadAPIRead)
def media_downloads_delete(media_download_id: int):
    return delete_media_download(media_download_id)
