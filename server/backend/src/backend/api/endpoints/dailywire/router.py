from fastapi import APIRouter
from .episodes import dw_episode_router
from .shows import dw_show_router
from .auth.router import router as dw_auth_router

router = APIRouter()

router.include_router(dw_episode_router, prefix="/episodes")
router.include_router(dw_show_router, prefix="/shows")
router.include_router(dw_auth_router, prefix="/auth")