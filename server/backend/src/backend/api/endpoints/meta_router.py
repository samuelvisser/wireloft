from fastapi import APIRouter

from .meta_service import *
from ..models.response import HealthResponse

router = APIRouter()

@router.get("/health", response_model=list[HealthResponse])
def health():
    return get_health()