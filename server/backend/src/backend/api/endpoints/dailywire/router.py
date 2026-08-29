from fastapi import APIRouter
from .auth import auth_router
from .episodes import dw_episode_router
from .shows import dw_show_router
from .user_info import dw_user_info_router
from .catalog import dw_catalog_router
from .movies import dw_movie_router

router = APIRouter(prefix="/dailywire")

router.include_router(auth_router)
router.include_router(dw_episode_router)
router.include_router(dw_show_router)
router.include_router(dw_user_info_router)
router.include_router(dw_catalog_router)
router.include_router(dw_movie_router)
