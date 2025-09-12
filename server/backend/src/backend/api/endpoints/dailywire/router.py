from fastapi import APIRouter
from .episodes import dw_episode_router
from .shows import dw_show_router

router = APIRouter()

router.include_router(dw_episode_router, prefix="/episodes")
router.include_router(dw_show_router, prefix="/shows")