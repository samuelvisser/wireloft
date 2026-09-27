from __future__ import annotations

import asyncio
from threading import Event

from dailywire_downloader import DownloadCancelled

from backend.services.show_assets import SHOW_ASSETS_REQUESTED
from task_manager.scheduler.registry import on_event, task

from .service import run_reconcile_show_assets


@on_event(event_name=SHOW_ASSETS_REQUESTED, resource_type="show")
@on_event(event_name="show.indexed", resource_type="show")
@on_event(event_name="show.updated", resource_type="show")
@on_event(event_name="download_profile.added", resource_type="download_profile")
@on_event(event_name="download_profile.updated", resource_type="download_profile")
@on_event(event_name="app.startup", resource_type="show")
@task(
    key="reconcile_show_assets",
    title="Reconcile show artwork",
    description="Download and reconcile shared show posters, backgrounds and square artwork.",
    allowed_resource_types=("show", "download_profile"),
    default_max_retries=3,
    tracks_progress=True,
)
async def reconcile_show_assets(*, resource_id: int | None = None, resource_type: str | None = None, progress=None):
    stopped = Event()

    def check_cancelled():
        if stopped.is_set() or (callable(progress) and progress()):
            raise DownloadCancelled("Show artwork reconciliation was canceled")

    # Sessions are created in the worker thread, never transferred between threads.
    # Cancellation must also reach the thread before it can publish downloaded bytes.
    try:
        await asyncio.to_thread(
            run_reconcile_show_assets, resource_id=resource_id, resource_type=resource_type,
            progress=progress, check_cancelled=check_cancelled,
        )
    finally:
        stopped.set()
