from fastapi import APIRouter

from .meta_service import *
from ..models.meta import *

router = APIRouter(prefix="/meta", tags=["Meta"])


@router.get("/health", response_model=HealthAPIRead)
def health():
    return get_health()