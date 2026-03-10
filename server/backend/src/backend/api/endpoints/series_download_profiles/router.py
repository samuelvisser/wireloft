from fastapi import APIRouter, status

from .service import *
from ...models.series_download_profile import *
from backend.app import db_session

router = APIRouter(prefix="/series-download-profiles", tags=["Download Profiles (series)"])

@router.get("", response_model=list[SeriesDownloadProfileAPIRead])
def series_download_profiles_list():
    """
    List all series download profiles in the system.

    Returns a collection of all download profile configurations for TV series and shows.
    """
    with db_session() as s:
        return get_series_download_profiles_list(s)


@router.post("", response_model=SeriesDownloadProfileAPIRead, status_code=status.HTTP_201_CREATED)
def series_download_profiles_create(body: SeriesDownloadProfileAPICreate):
    """
    Create a new series download profile.

    Creates a new profile defining download preferences for TV series including episode selection and media quality.
    Returns the created profile with tracking information.
    """
    with db_session() as s:
        try:
            result = create_download_profile_series(s, body)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.get("/{download_profile_series_id}", response_model=SeriesDownloadProfileAPIRead)
def series_download_profiles_detail(download_profile_series_id: int):
    """
    Retrieve detailed information for a specific series download profile.

    Returns complete profile configuration including show association and download preferences.
    """
    with db_session() as s:
        return get_download_profile_series(s, download_profile_series_id)


@router.patch("/{download_profile_series_id}", response_model=SeriesDownloadProfileAPIRead)
def series_download_profiles_update(download_profile_series_id: int, body: SeriesDownloadProfileAPIUpdate):
    """
    Update an existing series download profile.

    Partially updates profile configuration with the provided fields.
    Only specified fields will be modified; omitted fields remain unchanged.
    """
    with db_session() as s:
        try:
            result = update_download_profile_series(s, download_profile_series_id, body)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.delete("/{download_profile_series_id}", response_model=SeriesDownloadProfileAPIRead)
def series_download_profiles_delete(download_profile_series_id: int):
    """
    Delete a series download profile from the system.

    Permanently removes the specified profile configuration.
    Returns the deleted profile's information for confirmation.
    """
    with db_session() as s:
        try:
            result = await delete_download_profile_series(s, download_profile_series_id)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise
