from __future__ import annotations

from typing import Optional

from config import get_settings
from controller.db_utils import db_session
from task_manager.scheduler.registry import task, on_cron, on_event
from ..fetch_new_episodes.service import SHOW_INDEXED_EVENT
from .service import run_download_profile_worker
from task_manager.scheduler.registry import on_event, task
from ...helpers.episodes.events import EPISODE_IDENTIFIER_CHANGED_EVENT
from .identifier_changes import handle_episode_identifier_changed


@on_event(
    event_name=SHOW_INDEXED_EVENT,
    resource_type="show",
)
@on_event(
    event_name="download_profile.added",
    resource_type="download_profile",
)
@on_event(
    event_name="download_profile.updated",
    resource_type="download_profile",
)
@on_event(
    event_name="episode.published_final",
    resource_type="episode",
)
@on_event(
    event_name="episode.published_with_countdown",
    resource_type="episode",
)
@on_event(
    event_name="app.startup",
    resource_type="download_profile",
)
@on_cron(
    cron=get_settings().download_settings.verify_downloads_cron,
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
)
async def download_profile_worker(
        *,
        resource_id: Optional[int] = None,
        resource_type: Optional[str] = None,
        progress=None,
) -> None:
    """
    Ensures the episodes requested by enabled Download Profiles are downloaded.

    ``resource_id`` is polymorphic: an episode id when triggered by an episode
    publish event, a show id (checks the whole show's profiles), a specific
    download_profile id, or 0/None for a global sweep across every enabled profile
    (cron, app.startup, or a manual "show"/"download_profile" trigger).
    ``resource_type`` defines which one it is.
    """
    with db_session() as s:
        await run_download_profile_worker(
            s,
            resource_id=resource_id,
            resource_type=resource_type,
            progress=progress,
        )


@on_event(
    event_name=EPISODE_IDENTIFIER_CHANGED_EVENT,
    resource_type="episode",
)
@task(
    key="download_profile_identifier_change_worker",
    title="Repair downloads after identifier changes",
    description=(
        "Re-downloads affected episode files when a published episode identifier changes"
    ),
    allowed_resource_types=("episode",),
    default_max_retries=5,
    tracks_progress=False,
)
async def download_profile_identifier_change_worker(
        *,
        resource_id: Optional[int] = None,
        old_episode_identifier: Optional[str] = None,
        new_episode_identifier: Optional[str] = None,
        progress=None,
) -> None:
    """Repair Download Profile artifacts affected by an episode identifier change."""
    if resource_id is None:
        raise ValueError("Episode id is required for identifier-change handling")
    if old_episode_identifier is None or new_episode_identifier is None:
        raise ValueError(
            "Both old and new episode identifiers are required for identifier-change handling"
        )

    with db_session() as s:
        handle_episode_identifier_changed(
            s,
            episode_id=resource_id,
            old_episode_identifier=old_episode_identifier,
            new_episode_identifier=new_episode_identifier,
        )
