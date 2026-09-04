from fastapi import APIRouter

from backend.api.models.puller import FrontendPullAPIRead
from backend.app import db_session
from .service import get_frontend_pull


router = APIRouter(prefix="/pull", tags=["Frontend Puller"])


@router.get("", response_model=FrontendPullAPIRead)
def frontend_pull():
    """Return every payload currently delivered through frontend polling."""
    with db_session() as s:
        return get_frontend_pull(s)
