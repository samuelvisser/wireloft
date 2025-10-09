from fastapi import APIRouter
from .auth import auth_router
from .episodes import dw_episode_router
from .shows import dw_show_router

router = APIRouter(prefix="/dailywire")

router.include_router(auth_router)
router.include_router(dw_episode_router)
router.include_router(dw_show_router)