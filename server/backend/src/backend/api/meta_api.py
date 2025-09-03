from fastapi import APIRouter

from backend.services.meta import get_health
from backend.services.meta.response_models import HealthResponse

router = APIRouter()

@router.get("/list", response_model=list[HealthResponse])
def health():
    return get_health()