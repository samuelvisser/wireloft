from fastapi import APIRouter

from backend.services.show.service import get_show_list, get_show
from backend.services.show.response_models import ShowItem

router = APIRouter()

@router.get("/list", response_model=list[ShowItem])
def show_list():
    return get_show_list()

@router.get("/{show_id}", response_model=ShowItem)
def show_detail(show_id: int):
    return get_show(show_id)