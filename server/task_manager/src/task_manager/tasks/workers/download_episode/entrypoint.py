from __future__ import annotations

from typing import Optional

from controller.db_utils import db_session
from backend.db.models.media_download import EpisodeMediaDownload
from backend.db.models import Episode
from task_manager.tasks.helpers.custom_index_readiness import (
    custom_index_pair_lock, pair_is_ready, request_missing_index_repair,
    wait_for_custom_index_pair,
)
from backend.utils.custom_index import CustomIndexNotReadyError
from task_manager.scheduler.registry import task
from task_manager.tasks.media_download_operations import on_media_download_task_terminal
from task_manager.tasks.workers.download_attempt import serialize_download_attempt
from .service import run_download_episode


@task(
    key="download_episode",
    title="Download episode media",
    description="Downloads one episode's audio or video according to a Local Media Profile.",
    allowed_resource_types=("media_download",),
    default_max_retries=2,
    tracks_progress=True,
    terminal_callback=on_media_download_task_terminal,
    recovery_dispatcher=on_media_download_task_terminal,
)
async def download_episode(
        *,
        resource_id: Optional[int] = None,
        is_redownload: bool = False,
        progress=None,
):
    """Execute one MediaDownload artifact attempt.

    ``resource_id`` is the MediaDownload id. All changing execution state is
    owned by the TaskRun/TaskOperation that invoked this worker; the MediaDownload
    row contains only persistent artifact facts.
    """
    if resource_id is None:
        raise ValueError("A MediaDownload resource ID is required")

    with db_session() as session:
        download = session.get(EpisodeMediaDownload, resource_id)
        episode = session.get(Episode, download.media_item_id) if download is not None else None
        pair = (episode.show_id, download.local_media_profile_id) if episode is not None else None
    try:
        with serialize_download_attempt(resource_id):
            while True:
                if pair is not None:
                    await wait_for_custom_index_pair(*pair)
                    # Downloads only need to keep index/rename maintenance out. Other
                    # downloads for this same Show/Profile pair are safe to run alongside
                    # one another and must not collapse maxConcurrentDownloads to one.
                    async with custom_index_pair_lock(*pair, shared=True):
                        if not pair_is_ready(*pair):
                            continue
                        with db_session() as session:
                            return await run_download_episode(
                                session, media_download_id=resource_id,
                                is_redownload=is_redownload, progress=progress,
                            )
                with db_session() as session:
                    return await run_download_episode(
                        session, media_download_id=resource_id,
                        is_redownload=is_redownload, progress=progress,
                    )
    except CustomIndexNotReadyError as exc:
        request_missing_index_repair(exc)
        raise
