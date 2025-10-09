from __future__ import annotations

from contextlib import contextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy.exc import IntegrityError

from backend.api.errors import integrity_error_handler
from backend.db import get_session
from wireloft_config import get_settings


@contextmanager
def db_session():
    s = get_session()
    try:
        yield s
    finally:
        s.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="WireLoft API",
        summary="Internal API for WireLoft",
        version=get_settings().app_version,
    )

    # Allow the React dev server to call the API during development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Exception handlers
    app.add_exception_handler(IntegrityError, integrity_error_handler)

    # Import routers lazily to avoid circular imports during app module import
    from backend.api.endpoints import (
        dailywire_router,
        download_profile_podcast_router,
        download_profile_series_router,
        media_download_router,
        show_router,
        movie_router,
        episode_router,
        season_router,
        setting_router,
        media_profile_router,
        meta_router
    )

    app.include_router(dailywire_router, prefix="/api")
    app.include_router(download_profile_podcast_router, prefix="/api")
    app.include_router(download_profile_series_router, prefix="/api")
    app.include_router(episode_router, prefix="/api")
    app.include_router(season_router, prefix="/api")
    app.include_router(media_download_router, prefix="/api")
    app.include_router(show_router, prefix="/api")
    app.include_router(movie_router, prefix="/api")
    app.include_router(setting_router, prefix="/api")
    app.include_router(media_profile_router, prefix="/api")
    app.include_router(meta_router, prefix="/api")

    return app