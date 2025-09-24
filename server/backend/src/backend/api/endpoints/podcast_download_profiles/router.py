from fastapi import APIRouter, status

from .service import *
from ...models.download_profile_podcast import *
from ...app import db_session

router = APIRouter()

@router.get("", response_model=list[DownloadProfilePodcastAPIRead])
def podcast_download_profiles_list():
    with db_session() as s:
        return get_podcast_download_profiles_list(s)


@router.post("", response_model=DownloadProfilePodcastAPIRead, status_code=status.HTTP_201_CREATED)
def podcast_download_profiles_create(body: DownloadProfilePodcastAPICreate):
    with db_session() as s:
        try:
            result = create_download_profile_podcast(s, body)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.get("/{download_profile_podcast_id}", response_model=DownloadProfilePodcastAPIRead)
def podcast_download_profiles_detail(download_profile_podcast_id: int):
    with db_session() as s:
        return get_download_profile_podcast(s, download_profile_podcast_id)


@router.patch("/{download_profile_podcast_id}", response_model=DownloadProfilePodcastAPIRead)
def podcast_download_profiles_update(download_profile_podcast_id: int, body: DownloadProfilePodcastAPIUpdate):
    with db_session() as s:
        try:
            result = update_download_profile_podcast(s, download_profile_podcast_id, body)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.delete("/{download_profile_podcast_id}", response_model=DownloadProfilePodcastAPIRead)
def podcast_download_profiles_delete(download_profile_podcast_id: int):
    with db_session() as s:
        try:
            result = delete_download_profile_podcast(s, download_profile_podcast_id)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise
