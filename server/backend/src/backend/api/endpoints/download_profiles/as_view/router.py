from fastapi import APIRouter

from .service import *
from ....models.download_profile_view import DownloadProfileAPIReadView
from backend.app import db_session

router = APIRouter(prefix="/as-view")


@router.get("", response_model=list[DownloadProfileAPIReadView])
def download_profile_view_list():
    """
    List all download profiles with extended view information.

    Returns a collection of all download profiles with their base fields plus the show title
    and the local media profile preferred format. This is a denormalized view optimized for display.
    """
    with db_session() as s:
        return get_download_profile_views_list(s)


@router.get("/{download_profile_id}", response_model=DownloadProfileAPIReadView)
def download_profile_view_detail(download_profile_id: int):
    """
    Retrieve extended view information for a specific download profile.

    Returns base fields plus related show title and local media profile preferred format.
    """
    with db_session() as s:
        return get_download_profile_view(s, download_profile_id)
