from fastapi import APIRouter, status

from .service import *
from ....models.show import *
from backend.app import db_session

router = APIRouter(prefix = "/as-view")


@router.get("", response_model=list[ShowAPIReadView])
def show_view_list():
    """
    List all shows with extended view information.

    Returns a collection of all shows with their complete details including seasons, episodes, and profiles.
    This is a denormalized view optimized for display purposes.
    """
    with db_session() as s:
        return get_show_views_list(s)


@router.get("/{show_slug}", response_model=ShowAPIReadView)
def show_view_detail(show_slug: str):
    """
    Retrieve extended view information for a specific show.

    Returns complete show details including all nested relationships such as seasons, episodes, and download profiles.
    This is a denormalized view optimized for display purposes.
    """
    with db_session() as s:
        return get_show_view(s, show_slug)