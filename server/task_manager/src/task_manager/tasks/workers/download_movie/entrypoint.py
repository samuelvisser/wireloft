from __future__ import annotations

from typing import Optional

from controller.db_utils import db_session
from task_manager.scheduler.registry import task
from task_manager.tasks.workers.download_attempt import serialize_download_attempt

from .service import run_download_movie


@task(
    key="download_movie",
    title="Download movie media",
    description="Downloads one Daily Wire movie or movie extra according to a Movie Local Media Profile.",
    allowed_resource_types=("movie", "movie_extra"),
    default_max_retries=2,
    tracks_progress=True,
)
async def download_movie(
    *,
    resource_id: Optional[int] = None,
    media_download_id: int,
    attempt_generation: Optional[int] = None,
    progress=None,
) -> None:
    with serialize_download_attempt(media_download_id):
        with db_session() as session:
            await run_download_movie(
                session,
                media_download_id=media_download_id,
                attempt_generation=attempt_generation,
                progress=progress,
            )
