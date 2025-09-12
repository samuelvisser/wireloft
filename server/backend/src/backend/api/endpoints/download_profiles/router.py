from fastapi import APIRouter

from .service import *
from ...models.download_profile import *

router = APIRouter()

@router.get("", response_model=list[DownloadProfileAPIRead])
def download_profiles_list():
    return get_download_profiles_list()


@router.post("", response_model=DownloadProfileAPIRead)
def download_profiles_create(body: DownloadProfileAPICreate):
    return create_download_profile(body)


@router.get("/{download_profile_id}", response_model=DownloadProfileAPIRead)
def download_profiles_detail(download_profile_id: int):
    return get_download_profile(download_profile_id)


@router.patch("/{download_profile_id}", response_model=DownloadProfileAPIRead)
def download_profiles_update(download_profile_id: int, body: DownloadProfileAPIUpdate):
    return update_download_profile(download_profile_id, body)


@router.delete("/{download_profile_id}", response_model=DownloadProfileAPIRead)
def download_profiles_delete(download_profile_id: int):
    return delete_download_profile(download_profile_id)
