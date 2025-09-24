from fastapi import APIRouter, status

from .service import *
from ....models.show import *
from backend.app import db_session

router = APIRouter()


@router.get("", response_model=list[ShowAPIReadView])
def show_view_list():
    with db_session() as s:
        return get_show_views_list(s)


@router.get("/{show_slug}", response_model=ShowAPIReadView)
def show_view_detail(show_slug: str):
    with db_session() as s:
        return get_show_view(s, show_slug)