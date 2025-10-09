from fastapi import APIRouter, status

from .service import *
from ...models.download_profile_podcast import *
from backend.app import db_session

router = APIRouter(prefix="/podcast-download-profiles", tags=["Download Profiles (podcast)"])

@router.get("", response_model=list[DownloadProfilePodcastAPIRead])
def podcast_download_profiles_list():
    """
    List all podcast download profiles in the system.

    Returns a collection of all download profile configurations for podcasts.
    """
    with db_session() as s:
        return get_podcast_download_profiles_list(s)


@router.post("", response_model=DownloadProfilePodcastAPIRead, status_code=status.HTTP_201_CREATED)
def podcast_download_profiles_create(body: DownloadProfilePodcastAPICreate):
    """
    Create a new podcast download profile.

    Creates a new profile defining download preferences for podcasts including episode retention and audio quality.
    Returns the created profile with tracking information.
    """
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
    """
    Retrieve detailed information for a specific podcast download profile.

    Returns complete profile configuration including show association and download preferences.
    """
    with db_session() as s:
        return get_download_profile_podcast(s, download_profile_podcast_id)


@router.patch("/{download_profile_podcast_id}", response_model=DownloadProfilePodcastAPIRead)
def podcast_download_profiles_update(download_profile_podcast_id: int, body: DownloadProfilePodcastAPIUpdate):
    """
    Update an existing podcast download profile.

    Partially updates profile configuration with the provided fields.
    Only specified fields will be modified; omitted fields remain unchanged.
    """
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
    """
    Delete a podcast download profile from the system.

    Permanently removes the specified profile configuration.
    Returns the deleted profile's information for confirmation.
    """
    with db_session() as s:
        try:
            result = delete_download_profile_podcast(s, download_profile_podcast_id)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise
