from __future__ import annotations

from contextlib import contextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def create_app() -> FastAPI:
    app = FastAPI(title="DailyWire Local API")

    # Allow the React dev server or other tools to call the API during development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Lazy import to avoid circular deps on import
    from dailywire_api.api.endpoints import show_router

    app.include_router(show_router, prefix="/api/shows")

    return app
