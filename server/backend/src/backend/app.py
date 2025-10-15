from __future__ import annotations

from contextlib import contextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from sqlalchemy.exc import IntegrityError

from backend.api.errors import integrity_error_handler
from backend.db import get_session
from backend.security.auth import is_authenticated
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

    # Allow the React dev server to call the API during development (with credentials)
    # Configure allowed origins via WL_CORS_ORIGINS (comma-separated). Defaults include common Vite dev hosts.
    import os
    origins_env = os.environ.get("WL_CORS_ORIGINS", "").strip()
    if origins_env:
        allow_origins = [o.strip() for o in origins_env.split(",") if o.strip()]
    else:
        allow_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Exception handlers
    app.add_exception_handler(IntegrityError, integrity_error_handler)

    # Auth middleware to protect all API endpoints except /api/auth/*
    @app.middleware("http")
    async def _auth_guard(request: Request, call_next):
        # Allow CORS preflight requests to pass through without auth
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        # Protect all /api/* except public auth endpoints
        is_api = path.startswith("/api/")
        is_public_auth = path.startswith("/api/auth")
        is_public_config = path == "/api/config/public"
        if is_api and not (is_public_auth or is_public_config):
            if not is_authenticated(request):
                return JSONResponse({"detail": "Not authenticated"}, status_code=401)
        return await call_next(request)

    # Import routers lazily to avoid circular imports during app module import
    from backend.api.endpoints import (
        dailywire_router,
        download_profile_podcast_router,
        download_profile_series_router,
        download_profile_router,
        media_download_router,
        show_router,
        movie_router,
        episode_router,
        season_router,
        setting_router,
        local_media_profile_router,
        meta_router,
        config_router,
        rss_stream_profile_router,
        stream_profile_router,
        tasks_router,
    )
    from backend.api.endpoints.auth.router import router as auth_router

    # Public auth endpoints
    app.include_router(auth_router, prefix="/api")

    # Protected API endpoints (shielded by middleware above)
    app.include_router(dailywire_router, prefix="/api")
    app.include_router(download_profile_podcast_router, prefix="/api")
    app.include_router(download_profile_series_router, prefix="/api")
    app.include_router(download_profile_router, prefix="/api")
    app.include_router(episode_router, prefix="/api")
    app.include_router(season_router, prefix="/api")
    app.include_router(media_download_router, prefix="/api")
    app.include_router(show_router, prefix="/api")
    app.include_router(movie_router, prefix="/api")
    app.include_router(setting_router, prefix="/api")
    app.include_router(local_media_profile_router, prefix="/api")
    app.include_router(meta_router, prefix="/api")
    app.include_router(config_router, prefix="/api")
    app.include_router(rss_stream_profile_router, prefix="/api")
    app.include_router(stream_profile_router, prefix="/api")
    app.include_router(tasks_router, prefix="/api")

    # Start scheduler and sync task registry if enabled
    try:
        # Ensure controller tasks are imported so they are registered
        import wireloft_controller  # noqa: F401

        from wireloft_scheduler.scheduler import start_scheduler
        from wireloft_scheduler.registry import sync_registry_to_db
        if get_settings().scheduler.enabled:
            sync_registry_to_db()
            start_scheduler()
    except Exception:
        # Do not crash app if scheduler is not available
        pass

    return app