from fastapi import APIRouter

from .service import *
from ....models.stream_profile import StreamProfileAPIReadView
from backend.app import db_session

router = APIRouter(prefix="/as-view")


@router.get("", response_model=list[StreamProfileAPIReadView])
def stream_profile_view_list():
    """
    List all stream profiles with extended view information.

    Returns a collection of all stream profiles with their base fields plus the show title.
    This is a denormalized view optimized for display.
    """
    with db_session() as s:
        return get_stream_profile_views_list(s)


@router.get("/{stream_profile_id}", response_model=StreamProfileAPIReadView)
def stream_profile_view_detail(stream_profile_id: int):
    """
    Retrieve extended view information for a specific stream profile.

    Returns base fields plus related show title and concrete implementation payload.
    """
    with db_session() as s:
        return get_stream_profile_view(s, stream_profile_id)
