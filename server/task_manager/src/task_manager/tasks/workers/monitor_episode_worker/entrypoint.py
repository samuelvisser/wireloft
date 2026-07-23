from __future__ import annotations

from typing import Optional

from controller.db_utils import db_session
from task_manager.scheduler.registry import task
from .service import run_monitor_episode_worker


@task(
    key="monitor_episode_worker",
    title="Monitor live episode",
    description="Monitor and update status of currently live or not fully processed episode.",
    allowed_resource_types=("episode",),
    default_max_retries=5,
    tracks_progress=False,
)
async def monitor_episode_worker(
        *,
        resource_id: Optional[int] = None,
        slug: Optional[str] = None,
        progress=None,
        show_slug: Optional[str] = None,
        show_id: Optional[int] = None,
        season_id: Optional[int] = None,
        episode_identifier: Optional[str] = None,
        episode_index: Optional[int] = None,
) -> None:
    """
    Monitor and update the status of a currently live or not fully processed episode

    This worker runs frequently while an episode is live or not fully processed. It constantly checks whether there is
    a change in its publication status and updates the database accordingly.

    When an episode is found to be published, it also triggers the download worker

    Parameters:
    resource_id : Optional[int]
        The local ID of the episode to monitor if it exists in the database already
    slug : Optional[str]
        The slug of the episode to monitor
    progress : Any
        A progress tracker object, not supported by this worker

    Raises:
        Any raised exceptions during the execution of the database session
        or async tasks.
    """
    with db_session() as s:
        await run_monitor_episode_worker(
            s,
            episode_id=resource_id,
            episode_slug=slug,
            show_id=show_id,
            show_slug=show_slug,
            season_id=season_id,
            episode_identifier=episode_identifier,
            episode_index=episode_index,
        )
