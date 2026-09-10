from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from sqlalchemy.exc import IntegrityError

from backend.api.errors import integrity_error_handler
from backend.db import get_session
from backend.security.auth import is_authenticated
from config import get_settings


@contextmanager
def db_session():
    s = get_session()
    try:
        yield s
    finally:
        s.close()


def _is_committed_download_artifact(path, identity) -> bool:
    """Return whether the database owns this exact published media content."""
    from sqlalchemy import select

    from backend.db.models.media_download import MediaDownloadBase
    from backend.types.download_profile_types import MediaDownloadArtifactStatus

    session = get_session()
    try:
        statement = (
            select(
                MediaDownloadBase.artifact_stat_dev,
                MediaDownloadBase.artifact_stat_ino,
                MediaDownloadBase.artifact_size_bytes,
                MediaDownloadBase.artifact_fingerprint,
            )
            .where(
                MediaDownloadBase.file_path == str(path),
                MediaDownloadBase.artifact_status == MediaDownloadArtifactStatus.AVAILABLE.value,
            )
        )
        for row in session.execute(statement):
            # Content identity is the portable path for NAS/network filesystems,
            # whose inode/device identifiers may change between mounts. Keep the
            # filesystem identity fast path for older rows without a fingerprint.
            if (
                row.artifact_size_bytes == identity.size_bytes
                and row.artifact_fingerprint
                and row.artifact_fingerprint == identity.fingerprint
            ):
                return True
            if (
                row.artifact_stat_dev == identity.stat_dev
                and row.artifact_stat_ino == identity.stat_ino
            ):
                return True
        return False
    finally:
        session.close()


@asynccontextmanager
async def application_lifespan(app: FastAPI):
    """Own the background controller for exactly one ASGI app lifespan."""
    import controller
    from backend.utils.download_paths import (
        cleanup_abandoned_download_path_reservations,
        cleanup_abandoned_temporary_downloads,
    )

    settings = get_settings().download_settings
    # A killed download worker can leave either a direct-mode destination claim
    # or a private temporary-mode publication record behind. Reconcile both
    # before controller recovery can dispatch interrupted downloads again.
    cleanup_abandoned_download_path_reservations(settings.download_root)
    cleanup_abandoned_temporary_downloads(
        settings.temporary_download_root,
        settings.download_root,
        is_published_artifact=_is_committed_download_artifact,
    )

    started = False
    try:
        controller.start_controller()
        started = True
        yield
    finally:
        if started:
            controller.stop_controller()


def create_app() -> FastAPI:
    app = FastAPI(
        title="WireLoft API",
        summary="Internal API for WireLoft",
        version=get_settings().app_version,
        lifespan=application_lifespan,
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
        onboarding_router,
        operation_router,
        puller_router,
        episode_router,
        season_router,
        setting_router,
        local_media_profile_router,
        meta_router,
        config_router,
        rss_stream_profile_router,
        stream_profile_router,
        task_router,
        feeds_router,
    )
    from backend.api.endpoints.auth.router import router as auth_router

    # Public auth endpoints
    app.include_router(auth_router, prefix="/api")

    # Podcast feed endpoints: intentionally mounted outside /api (and thus
    # outside the auth middleware below) so feed URLs keep working in podcast
    # apps even when local auth is enabled. Secured instead by an unguessable
    # per-profile token baked into the URL - see backend.api.endpoints.feeds.
    app.include_router(feeds_router)

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
    app.include_router(onboarding_router, prefix="/api")
    app.include_router(operation_router, prefix="/api")
    app.include_router(puller_router, prefix="/api")
    app.include_router(setting_router, prefix="/api")
    app.include_router(local_media_profile_router, prefix="/api")
    app.include_router(meta_router, prefix="/api")
    app.include_router(config_router, prefix="/api")
    app.include_router(rss_stream_profile_router, prefix="/api")
    app.include_router(stream_profile_router, prefix="/api")
    app.include_router(task_router, prefix="/api")

    return app
