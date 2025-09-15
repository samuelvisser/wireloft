from fastapi import APIRouter

from .service import *
from ...models.download_profile_series import *

router = APIRouter()

@router.get("", response_model=list[DownloadProfileSeriesAPIRead])
def series_download_profiles_list():
    return get_series_download_profiles_list()


@router.post("", response_model=DownloadProfileSeriesAPIRead)
def series_download_profiles_create(body: DownloadProfileSeriesAPICreate):
    return create_download_profile_series(body)


@router.get("/{download_profile_series_id}", response_model=DownloadProfileSeriesAPIRead)
def series_download_profiles_detail(download_profile_series_id: int):
    return get_download_profile_series(download_profile_series_id)


@router.patch("/{download_profile_series_id}", response_model=DownloadProfileSeriesAPIRead)
def series_download_profiles_update(download_profile_series_id: int, body: DownloadProfileSeriesAPIUpdate):
    return update_download_profile_series(download_profile_series_id, body)


@router.delete("/{download_profile_series_id}", response_model=DownloadProfileSeriesAPIRead)
def series_download_profiles_delete(download_profile_series_id: int):
    return delete_download_profile_series(download_profile_series_id)
