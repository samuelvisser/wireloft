from __future__ import annotations

from typing import Optional

from controller.db_utils import db_session
from task_manager.scheduler.registry import task

from .service import run_download_movie


@task(
    key="download_movie",
    title="Download movie",
    description="Downloads one Daily Wire movie according to a Local Media Profile.",
    allowed_resource_types=("movie",),
    default_max_retries=2,
    tracks_progress=True,
)
async def download_movie(
    *,
    resource_id: Optional[int] = None,
    media_download_id: int,
    progress=None,
) -> None:
    with db_session() as session:
        await run_download_movie(session, media_download_id=media_download_id, progress=progress)
