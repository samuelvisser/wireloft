from fastapi import APIRouter, Request, status

from .service import *
from ....models.show import ShowAPIRead
from ....models.show_as_bundle import ShowAPICreateBundle
from backend.app import db_session

router = APIRouter(prefix = "/as-bundle")


@router.post("", response_model=ShowAPIRead, status_code=status.HTTP_201_CREATED)
def show_create_as_bundle(body: ShowAPICreateBundle, request: Request):
    """
    Create a new show, optionally with media, download, and stream profiles in a single operation.
    """
    with db_session() as s:
        try:
            result = create_show_bundle(s, request, body)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise
