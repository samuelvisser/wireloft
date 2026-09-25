from __future__ import annotations

from contextlib import AsyncExitStack

from controller.db_utils import db_session
from backend.db.models import Episode
from backend.db.models.media_download import EpisodeMediaDownload
from sqlalchemy import select
from task_manager.tasks.helpers.custom_index_readiness import (
    custom_index_pair_lock, pair_is_ready, request_missing_index_repair,
    wait_for_custom_index_pair,
)
from backend.utils.custom_index import CustomIndexNotReadyError
from task_manager.scheduler.registry import on_event, task
from task_manager.scheduler.results import TaskResult
from task_manager.tasks.helpers.episodes.events import EPISODE_IDENTIFIER_CHANGED_EVENT
from .service import run_rename_file_worker


@on_event(EPISODE_IDENTIFIER_CHANGED_EVENT, resource_type="episode")
@task(
    key="rename_file_worker",
    title="Rename episode file",
    description="Rename existing episode files to match their current output templates and metadata.",
    allowed_resource_types=("episode",),
    default_max_retries=2,
    tracks_progress=True,
)
async def rename_file_worker(
        *,
        resource_id: int | None = None,
        progress=None,
        local_media_profile_id: int | None = None,
        identifier_fields_only: bool = False,
        old_episode_identifier: str | None = None,
        new_episode_identifier: str | None = None,
) -> TaskResult:
    """Rename existing files for one episode in the requested Local Media Profile scope."""
    if resource_id is None:
        raise ValueError("Rename File requires an episode resource")

    identifier_event = (
        old_episode_identifier is not None
        and new_episode_identifier is not None
    )

    with db_session() as s:
        episode = s.get(Episode, resource_id)
        profile_ids = tuple(s.scalars(select(EpisodeMediaDownload.local_media_profile_id).where(
            EpisodeMediaDownload.media_item_id == resource_id,
            *([EpisodeMediaDownload.local_media_profile_id == local_media_profile_id]
              if local_media_profile_id is not None else []),
        ).distinct()))
        show_id = episode.show_id if episode is not None else None
    try:
        while True:
            if show_id is not None:
                for profile_id in profile_ids:
                    await wait_for_custom_index_pair(show_id, profile_id)
            async with AsyncExitStack() as locks:
                if show_id is not None:
                    for profile_id in sorted(profile_ids):
                        await locks.enter_async_context(custom_index_pair_lock(show_id, profile_id))
                    if not all(pair_is_ready(show_id, profile_id) for profile_id in profile_ids):
                        continue
                with db_session() as s:
                    return await run_rename_file_worker(
                        s,
                        episode_id=resource_id,
                        local_media_profile_id=local_media_profile_id,
                        identifier_fields_only=identifier_fields_only or identifier_event,
                        progress=progress,
                    )
    except CustomIndexNotReadyError as exc:
        request_missing_index_repair(exc)
        raise
