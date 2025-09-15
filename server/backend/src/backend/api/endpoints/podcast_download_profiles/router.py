from fastapi import APIRouter

from .service import *
from ...models.download_profile_podcast import *

router = APIRouter()

@router.get("", response_model=list[DownloadProfilePodcastAPIRead])
def podcast_download_profiles_list():
    return get_podcast_download_profiles_list()


@router.post("", response_model=DownloadProfilePodcastAPIRead)
def podcast_download_profiles_create(body: DownloadProfilePodcastAPICreate):
    return create_download_profile_podcast(body)


@router.get("/{download_profile_podcast_id}", response_model=DownloadProfilePodcastAPIRead)
def podcast_download_profiles_detail(download_profile_podcast_id: int):
    return get_download_profile_podcast(download_profile_podcast_id)


@router.patch("/{download_profile_podcast_id}", response_model=DownloadProfilePodcastAPIRead)
def podcast_download_profiles_update(download_profile_podcast_id: int, body: DownloadProfilePodcastAPIUpdate):
    return update_download_profile_podcast(download_profile_podcast_id, body)


@router.delete("/{download_profile_podcast_id}", response_model=DownloadProfilePodcastAPIRead)
def podcast_download_profiles_delete(download_profile_podcast_id: int):
    return delete_download_profile_podcast(download_profile_podcast_id)
