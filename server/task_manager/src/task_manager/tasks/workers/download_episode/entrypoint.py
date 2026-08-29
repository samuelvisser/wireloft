from __future__ import annotations

from typing import Optional

from controller.db_utils import db_session
from task_manager.scheduler.registry import task
from task_manager.tasks.workers.download_attempt import serialize_download_attempt
from .service import run_download_episode


@task(
    key="download_episode",
    title="Download episode media",
    description="Downloads one episode's audio or video according to a Local Media Profile.",
    allowed_resource_types=("episode",),
    default_max_retries=2,
    tracks_progress=True,
)
async def download_episode(
        *,
        resource_id: Optional[int] = None,
        media_download_id: int,
        attempt_generation: Optional[int] = None,
        is_redownload: bool = False,
        progress=None,
) -> None:
    """Download one episode according to the referenced media download row.

    ``media_download_id`` points at the EpisodeMediaDownload row created when the
    download was requested; it carries the episode and the Local Media Profile.
    ``resource_id`` is the episode id, used only for task-run bookkeeping.
    ``is_redownload`` marks a re-fetch of an episode that was already downloaded
    (e.g. a Download Profile replacing a countdown-era file once the episode goes
    final): the row is marked REDOWNLOADED instead of DOWNLOADED on success.
    """
    with serialize_download_attempt(media_download_id):
        with db_session() as s:
            await run_download_episode(
                s,
                media_download_id=media_download_id,
                attempt_generation=attempt_generation,
                is_redownload=is_redownload,
                progress=progress,
            )
