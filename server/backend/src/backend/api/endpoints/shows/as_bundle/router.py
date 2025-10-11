from fastapi import APIRouter, status

from .service import *
from ....models.show import ShowAPIRead
from ....models.show_as_bundle import ShowAPICreateBundle
from backend.app import db_session

router = APIRouter(prefix = "/as-bundle")


@router.post("", response_model=ShowAPIRead, status_code=status.HTTP_201_CREATED)
def show_create_with_profiles(body: ShowAPICreateBundle):
    """
    Create a new show with media- and download profiles in a single operation.

    Creates a show along with its associated download profiles (series or podcast) in one atomic transaction.
    This is a convenience endpoint for setting up a complete show configuration at once.
    Returns the created show with basic metadata.
    """
    with db_session() as s:
        try:
            result = create_show_bundle(s, body)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise
