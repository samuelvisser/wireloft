from fastapi import APIRouter

from backend.services.meta.service import get_health
from backend.services.meta.response_models import HealthResponse

router = APIRouter()

@router.get("", response_model=list[HealthResponse])
def health():
    return get_health()