from __future__ import annotations

from typing import Optional

from wireloft_controller.app import db_session
from wireloft_controller.tasks.registry import task
from .service import run_new_episode_finder


@task(
    key="new_episode_finder",
    title="Find new episodes in all shows",
    description="Finds new episodes in all shows.",
    allowed_resource_types=("show",),
    default_max_retries=5,
    tracks_progress=False,
)
async def new_episode_finder(*, resource_id: Optional[int] = None, slug: Optional[str] = None, progress=None) -> None:
    """
    Finds new episodes in all shows.

    This worker searches for new episodes across all shows. It retrieves
    new episodes using the provided parameters and updates the database.

    Parameters:
    resource_id : Optional[int]
        The ID of a specific show if the task needs to focus on one.
    slug : Optional[str]
        The slug of a specific show if the task needs to focus on one.
    progress : Any
        A progress tracker object.

    Raises:
        Any raised exceptions during the execution of the database session
        or async tasks.
    """
    with db_session() as s:
        await run_new_episode_finder(s, show_id=resource_id, show_slug=slug, progress=progress)