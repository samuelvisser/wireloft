from fastapi import APIRouter, status

from .service import *
from ....models.show import ShowAPIRead
from ....models.show_with_profiles import ShowAPICreateBundle
from backend.app import db_session

router = APIRouter()


@router.post("", response_model=ShowAPIRead, status_code=status.HTTP_201_CREATED)
def show_create_with_profiles(body: ShowAPICreateBundle):
    with db_session() as s:
        try:
            result = create_show_bundle(s, body)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise
