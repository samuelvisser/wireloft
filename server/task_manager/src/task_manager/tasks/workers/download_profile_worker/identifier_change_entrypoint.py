from __future__ import annotations

from typing import Optional

from controller.db_utils import db_session
from task_manager.scheduler.registry import on_event, task
from ...helpers.episodes.events import EPISODE_IDENTIFIER_CHANGED_EVENT
from .identifier_changes import handle_episode_identifier_changed


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
