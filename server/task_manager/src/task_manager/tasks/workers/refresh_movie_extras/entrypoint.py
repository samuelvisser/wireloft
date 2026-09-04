from __future__ import annotations

from typing import Optional

from controller.db_utils import db_session
from task_manager.scheduler.registry import task
from task_manager.scheduler.results import TaskResult

from .service import run_refresh_movie_extras


@task(
    key="refresh_movie_extras",
    title="Refresh movie extras",
    description="Fetches a Daily Wire movie page and indexes any new movie extras.",
    allowed_resource_types=("movie",),
    default_max_retries=2,
    tracks_progress=True,
)
async def refresh_movie_extras(
    *,
    resource_id: Optional[int] = None,
    progress=None,
) -> TaskResult:
    if resource_id is None:
        raise ValueError("A movie resource ID is required")
    with db_session() as session:
        added = await run_refresh_movie_extras(
            session,
            movie_id=resource_id,
            progress=progress,
        )

    return TaskResult(
        summary=(
            f"Movie extras refreshed: {added} new "
            f"{'extra' if added == 1 else 'extras'} added"
        ),
        data={"movie_extras_added": added},
    )
