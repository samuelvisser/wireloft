from fastapi import APIRouter, status

from .service import *
from ...models.download_profile_series import *
from backend.app import db_session

router = APIRouter()

@router.get("", response_model=list[DownloadProfileSeriesAPIRead])
def series_download_profiles_list():
    with db_session() as s:
        return get_series_download_profiles_list(s)


@router.post("", response_model=DownloadProfileSeriesAPIRead, status_code=status.HTTP_201_CREATED)
def series_download_profiles_create(body: DownloadProfileSeriesAPICreate):
    with db_session() as s:
        try:
            result = create_download_profile_series(s, body)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.get("/{download_profile_series_id}", response_model=DownloadProfileSeriesAPIRead)
def series_download_profiles_detail(download_profile_series_id: int):
    with db_session() as s:
        return get_download_profile_series(s, download_profile_series_id)


@router.patch("/{download_profile_series_id}", response_model=DownloadProfileSeriesAPIRead)
def series_download_profiles_update(download_profile_series_id: int, body: DownloadProfileSeriesAPIUpdate):
    with db_session() as s:
        try:
            result = update_download_profile_series(s, download_profile_series_id, body)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.delete("/{download_profile_series_id}", response_model=DownloadProfileSeriesAPIRead)
def series_download_profiles_delete(download_profile_series_id: int):
    with db_session() as s:
        try:
            result = delete_download_profile_series(s, download_profile_series_id)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise
