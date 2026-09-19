from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager, contextmanager

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from sqlalchemy.exc import IntegrityError

from backend.api.errors import integrity_error_handler
from backend.db import get_session
from backend.security.auth import is_authenticated
from config import get_settings
from config.network import NO_INTERNET_CONNECTION_MESSAGE, is_no_internet_error


logger = logging.getLogger(__name__)


@contextmanager
def db_session():
    s = get_session()
    try:
        yield s
    finally:
        s.close()


def _recover_download_filesystem(download_settings, scheduled_work_pause) -> None:
    """Reconcile crash leftovers without delaying API readiness.

    The caller acquires a scheduled-work pause before controller startup and
    hands that lease to this background thread. Other critical work may hold its
    own lease at the same time; normal work resumes only after the final lease is
    released.
    """
    from task_manager.tasks.helpers.downloads.download_paths import (
        cleanup_abandoned_download_path_reservations,
        cleanup_abandoned_temporary_downloads,
    )

    try:
        logger.info("Starting background download filesystem recovery")
        reservation_count = cleanup_abandoned_download_path_reservations(
            download_settings.download_root
        )
        temporary_count = cleanup_abandoned_temporary_downloads(
            download_settings.temporary_download_root,
            download_settings.download_root,
        )
        logger.info(
            "Download filesystem recovery complete: cleaned %s stale path claim(s) and %s temporary workspace(s)",
            reservation_count,
            temporary_count,
        )
    except Exception:
        # Filesystem recovery is best-effort crash cleanup. A transient mount or
        # permissions problem must not leave every background task paused forever.
        logger.exception(
            "Download filesystem recovery failed; releasing its scheduled-work pause without complete cleanup"
        )
    finally:
        scheduled_work_pause.release()


@asynccontextmanager
async def application_lifespan(app: FastAPI):
    """Own the background controller for exactly one ASGI app lifespan."""
    import controller
    from task_manager.scheduler.scheduler import (
        pause_scheduled_work,
        start_scheduler,
    )

    settings = get_settings()

    # Acquire the filesystem-recovery lease before controller startup so no
    # normal job can slip through while durable work is being restored. Critical
    # tasks (for example background migrations) use their own scheduler lane and
    # may start while this lease is active.
    start_scheduler()
    filesystem_pause = pause_scheduled_work(
        "download filesystem recovery",
        owner_key="startup-download-filesystem-recovery",
    )

    started = False
    recovery_started = False
    try:
        controller.start_controller()
        started = True

        recovery_thread = threading.Thread(
            target=_recover_download_filesystem,
            args=(settings.download_settings, filesystem_pause),
            name="wireloft-startup-download-recovery",
            daemon=True,
        )
        recovery_thread.start()
        recovery_started = True
        yield
    finally:
        if not recovery_started:
            filesystem_pause.release()
        if started:
            controller.stop_controller()


async def _network_aware_http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
):
    """Normalize HTTP errors whose underlying cause is a local internet outage."""
    if is_no_internet_error(exc):
        logger.warning(NO_INTERNET_CONNECTION_MESSAGE)
        return JSONResponse(
            {"detail": NO_INTERNET_CONNECTION_MESSAGE},
            status_code=503,
        )
    return await http_exception_handler(request, exc)


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
    app.add_exception_handler(StarletteHTTPException, _network_aware_http_exception_handler)

    # Auth middleware to protect all API endpoints except /api/auth/*
    @app.middleware("http")
    async def _auth_guard(request: Request, call_next):
        try:
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
        except Exception as exc:
            # External HTTP clients use several libraries. Normalize only strong
            # local-connectivity signals here so ordinary upstream/API failures keep
            # their existing diagnostics and status handling.
            if not is_no_internet_error(exc):
                raise
            logger.warning(NO_INTERNET_CONNECTION_MESSAGE)
            return JSONResponse(
                {"detail": NO_INTERNET_CONNECTION_MESSAGE},
                status_code=503,
            )

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
        custom_metadata_router,
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
    app.include_router(custom_metadata_router, prefix="/api")
    app.include_router(meta_router, prefix="/api")
    app.include_router(config_router, prefix="/api")
    app.include_router(rss_stream_profile_router, prefix="/api")
    app.include_router(stream_profile_router, prefix="/api")
    app.include_router(task_router, prefix="/api")

    return app