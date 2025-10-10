from __future__ import annotations

from fastapi import APIRouter

from .service import get_public_config
from ...models.config_public import ConfigPublicRead

router = APIRouter(prefix="/config", tags=["Config"])


@router.get("/public", response_model=ConfigPublicRead)
def read_public_config():
    return get_public_config()
