from fastapi import APIRouter

from .service import *
from .as_view import download_profile_view_router
from ...models.download_profile import *
from backend.app import db_session

router = APIRouter(prefix="/download-profiles", tags=["Download Profiles (base)"])

# Mount sub-routers
router.include_router(download_profile_view_router)


@router.get("", response_model=list[DownloadProfileAPIRead])
def download_profiles_list():
    """
    List all download profiles (any type).
    """
    with db_session() as s:
        return get_download_profiles_list(s)


@router.get("/by-show-slug/{show_slug}", response_model=list[DownloadProfileAPIRead])
def download_profiles_by_show_slug_list(show_slug: str):
    """
    List all download profiles in any show.
    """
    with db_session() as s:
        return get_download_profiles_list(s, show_slug)


@router.get("/{download_profile_id}", response_model=DownloadProfileAPIRead)
def download_profile_detail(download_profile_id: int):
    """
    Retrieve a single download profile by its base id.
    """
    with db_session() as s:
        return get_download_profile(s, download_profile_id)
