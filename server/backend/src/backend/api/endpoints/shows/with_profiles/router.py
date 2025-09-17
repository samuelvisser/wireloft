from fastapi import APIRouter, status

from .service import *
from ....models.show import ShowAPIRead
from ....models.show_with_profiles import ShowAPICreateBundle

router = APIRouter()


@router.post("", response_model=ShowAPIRead, status_code=status.HTTP_201_CREATED)
def show_create_with_profiles(body: ShowAPICreateBundle):
    return create_show_bundle(body)
