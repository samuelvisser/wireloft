from fastapi import APIRouter

from backend.api.models.puller import FrontendPullAPIRead
from .service import get_frontend_pull


router = APIRouter(prefix="/pull", tags=["Frontend Puller"])


@router.get("", response_model=FrontendPullAPIRead)
def frontend_pull():
    """Return WireLoft's generic changing-execution snapshot."""
    return get_frontend_pull()
