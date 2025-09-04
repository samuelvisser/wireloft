from __future__ import annotations

from contextlib import contextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.db import get_session

@contextmanager
def db_session():
    s = get_session()
    try:
        yield s
    finally:
        s.close()


def create_app() -> FastAPI:
    app = FastAPI(title="WireLoft API")

    # Allow the React dev server to call the API during development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Import routers lazily to avoid circular imports during app module import
    from backend.api import show_router, episode_router, setting_router, media_profile_router, meta_router

    app.include_router(show_router, prefix="/api/show")
    app.include_router(episode_router, prefix="/api/show/{show_slug}/episode")
    app.include_router(setting_router, prefix="/api/setting")
    app.include_router(media_profile_router, prefix="/api/media-profile")
    app.include_router(meta_router, prefix="/api/meta")

    return app