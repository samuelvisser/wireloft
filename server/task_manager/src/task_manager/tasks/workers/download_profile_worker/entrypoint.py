from __future__ import annotations

from typing import Optional

from config import get_settings
from controller.db_utils import db_session
from backend.utils.custom_index import CustomIndexNotReadyError
from task_manager.tasks.helpers.custom_index_readiness import request_missing_index_repair
from .event_adapter import DOWNLOAD_PROFILE_RUN_REQUESTED_EVENT
from task_manager.scheduler.registry import on_cron, on_event, task
from task_manager.tasks.media_download_operations import on_media_download_task_terminal
from .service import run_download_profile_worker


@on_event(
    event_name=DOWNLOAD_PROFILE_RUN_REQUESTED_EVENT,
)
@on_event(
    event_name="app.startup",
    resource_type="download_profile",
)
@on_cron(
    cron=get_settings().download_settings.verify_downloads_cron,
    enabled=get_settings().download_settings.verify_downloads_cron_enabled,
    minimum_interval_ms=get_settings().dw_timeout.min_slow_request_ms,
    resource_type="download_profile",
    resource_id=0,
    coalesce=True,
)
@task(
    key="download_profile_worker",
    title="Run Download Profiles",
    description="Makes sure Download Profiles actually work by downloading the episodes they request",
    allowed_resource_types=("download_profile", "show", "episode"),
    default_max_retries=5,
    tracks_progress=True,
    terminal_callback=on_media_download_task_terminal,
)
async def download_profile_worker(
        *,
        resource_id: Optional[int] = None,
        resource_type: Optional[str] = None,
        progress=None,
) -> None:
    """
    Ensures the episodes requested by enabled Download Profiles are downloaded.

    ``resource_id`` is polymorphic: an episode id for an episode-scoped request,
    a show id (checks the whole show's profiles), a specific download_profile id,
    or 0/None for a global sweep across every enabled profile (cron or app.startup).
    ``resource_type`` defines which one it is. The Download Profile event adapter
    translates normal committed domain events into the scoped worker-only request.

    Profile enablement only controls admission of new automatic downloads. Once
    a ``media.download`` operation is queued, the terminal callback gives the
    shared download dispatcher a chance to start it regardless of the profile's
    current enabled state.
    """
    try:
        with db_session() as s:
            await run_download_profile_worker(
                s,
                resource_id=resource_id,
                resource_type=resource_type,
                progress=progress,
            )
    except CustomIndexNotReadyError as exc:
        request_missing_index_repair(exc)
        raise
