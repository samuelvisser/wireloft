from fastapi import APIRouter

from backend.services.show.service import get_show_list, get_show
from backend.services.show.response_models import ShowItemResponse

router = APIRouter()

@router.get("/list", response_model=list[ShowItemResponse])
def show_list():
    return get_show_list()

@router.get("/{show_slug}", response_model=ShowItemResponse)
def show_detail(show_slug: str):
    return get_show(show_slug)