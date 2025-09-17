from fastapi import APIRouter, status

from .service import *
from ....models.show import ShowAPIReadView

router = APIRouter()


@router.get("", response_model=list[ShowAPIReadView])
def show_view_list():
    return get_show_views_list()


@router.get("/{show_slug}", response_model=ShowAPIReadView)
def show_view_detail(show_slug: str):
    return get_show_view(show_slug)