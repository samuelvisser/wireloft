from fastapi import APIRouter, status

from .service import *
from ...models.media_download import *
from backend.app import db_session

router = APIRouter(prefix="/media-downloads", tags=["Media Downloads"])

@router.get("", response_model=list[MediaDownloadAPIRead])
def media_downloads_list():
    """
    List all media downloads in the system.

    Returns a collection of all media download records including status and progress.
    """
    with db_session() as s:
        return get_media_downloads_list(s)


@router.post("", response_model=MediaDownloadAPIRead, status_code=status.HTTP_201_CREATED)
def media_downloads_create(body: MediaDownloadAPICreate):
    """
    Create a new media download task.

    Initiates a new download operation for the specified media with the provided configuration.
    Returns the created download task with tracking information.
    """
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
    """
    Retrieve detailed information for a specific media download.

    Returns complete download information including status, progress, and file location.
    """
    with db_session() as s:
        return get_media_download(s, media_download_id)


@router.patch("/{media_download_id}", response_model=MediaDownloadAPIRead)
def media_downloads_update(media_download_id: int, body: MediaDownloadAPIUpdate):
    """
    Update an existing media download's metadata or status.

    Partially updates download information with the provided fields.
    Only specified fields will be modified; omitted fields remain unchanged.
    """
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
    """
    Delete a media download record from the system.

    Permanently removes the download record. Note: This does not delete the downloaded file.
    Returns the deleted download's information for confirmation.
    """
    with db_session() as s:
        try:
            result = delete_media_download(s, media_download_id)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise
